"""#490 §2.1 — the DATE-KEYED prev_close cross-check in Pass-2 (ships as a BUG FIX regardless
of the cutover).

The bug (design §1.2, 190/190 proof): pre-open, Alpaca's `previous_daily_bar` deterministically
holds the T-2 close (today's bar doesn't exist yet, both fields shift back a day). The old
field-hardcoded compare read T-2 as a "mismatch" and silently dropped the RT read of EVERY
candidate whose prior day moved >0.5% — censoring the pre-open shadow evidence
(ep_rt_floor_flip_up 29 RTH vs 2 pre-open). Fix: select whichever Alpaca bar (daily_bar OR
previous_daily_bar) has bar-date == the KNOWN previous trading date; neither matches → no
cross-check + prev_close UNVERIFIED → any authoritative RT-only flip-up additionally requires
Q3 bar corroboration. Also pins the C1 fix (the 30pp clamp is LOUD now: ep_rt_gap_clamped)
and §6.4 current_price coherence.
"""
import asyncio
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from agents.market_intelligence import ep_detector

_ET = ZoneInfo("America/New_York")
_PREV = date(2026, 7, 23)      # the known previous trading date
_T2 = date(2026, 7, 22)        # the day before it


def _now(h=7, m=30):
    return datetime(2026, 7, 24, h, m, 0, tzinfo=_ET)


def _bar_ts(d: date):
    return datetime(d.year, d.month, d.day, 0, 0, tzinfo=_ET)


def _wire(monkeypatch, *, authoritative=False):
    monkeypatch.setattr(ep_detector, "EP_RT_PASS2_ENABLED", True)

    async def _toggle(name, env, default=True):
        return authoritative
    monkeypatch.setattr(ep_detector, "get_runtime_toggle", _toggle)
    monkeypatch.setattr(ep_detector, "_audit_dedupe_check", lambda *a, **k: True)
    monkeypatch.setattr(ep_detector, "_rt_fresh_seen", set())
    monkeypatch.setattr(ep_detector, "_rt_fresh_seen_date", None)
    logged = []

    async def _log(event_type, summary, detail=""):
        logged.append(event_type)
    monkeypatch.setattr(ep_detector, "log_audit_event", _log)
    return logged


def _pass2(cands, snaps, now, prev_trade_date=_PREV):
    return asyncio.run(ep_detector._apply_realtime_pass2(
        cands, now, prev_trade_date=prev_trade_date, snaps=snaps))


def _cand(gap=12.0, pc=38.17):
    return {"ticker": "TRAX", "gap_pct": gap, "prev_close": pc,
            "gap_pct_delayed": gap, "current_price": pc * (1 + gap / 100),
            "price_source": "polygon_delayed"}


# ── THE bug fix: pre-open T-2 no longer censors the rt read ────────────────────────────────

def test_preopen_t2_prev_daily_bar_no_longer_mismatches(monkeypatch):
    logged = _wire(monkeypatch)
    now = _now()
    # Pre-open shape: previous_daily_bar = T-2 close 35.00 (an 8.3% "disagreement" vs Polygon's
    # 38.17 — the prior day's real move), daily_bar = T-1 close 38.17 matching Polygon exactly.
    sn = {"price": 42.0, "price_ts": now - timedelta(seconds=5),
          "prev_close": 35.00, "prev_daily_bar_ts": _bar_ts(_T2),
          "daily_bar_close": 38.17, "daily_bar_ts": _bar_ts(_PREV)}
    cands = [_cand()]
    out = _pass2(cands, {"TRAX": sn}, now)
    assert "ep_rt_prev_close_mismatch" not in logged      # the censoring bug is gone
    assert out[0]["gap_pct_rt"] == round((42.0 - 38.17) / 38.17 * 100, 2)
    assert out[0]["prev_close_verified"] is True
    assert out[0]["prev_close_alpaca"] == 38.17           # the date-matched reference


def test_true_date_matched_disagreement_still_degrades(monkeypatch):
    logged = _wire(monkeypatch)
    now = _now()
    # The date-matched bar itself disagrees >0.5% → a REAL data-quality signal → degrade.
    sn = {"price": 42.0, "price_ts": now - timedelta(seconds=5),
          "prev_close": 35.00, "prev_daily_bar_ts": _bar_ts(_T2),
          "daily_bar_close": 39.00, "daily_bar_ts": _bar_ts(_PREV)}
    out = _pass2([_cand()], {"TRAX": sn}, now)
    assert "ep_rt_prev_close_mismatch" in logged
    assert "gap_pct_rt" not in out[0]                     # rt read dropped — delayed decides


def test_neither_bar_matches_means_no_cross_check_unverified(monkeypatch):
    logged = _wire(monkeypatch)
    now = _now()
    # Post-holiday class / Alpaca gap: neither bar-date is the known prev trading date.
    sn = {"price": 42.0, "price_ts": now - timedelta(seconds=5),
          "prev_close": 35.00, "prev_daily_bar_ts": _bar_ts(_T2),
          "daily_bar_close": 38.17, "daily_bar_ts": _bar_ts(date(2026, 7, 24))}
    out = _pass2([_cand()], {"TRAX": sn}, now)
    assert "ep_rt_prev_close_mismatch" not in logged      # no wrong-day compare, ever
    assert out[0]["prev_close_verified"] is False
    assert "gap_pct_rt" in out[0]                         # rt still rides along (shadow value)


# ── §2.1 never-loosen: unverified prev_close + authoritative flip-up requires Q3 ───────────

def _flip_cand():
    # Superset-only admit: delayed 6% < 10 ≤ rt — the RT-only admission class.
    return {"ticker": "TRAX", "gap_pct": 6.0, "prev_close": 10.0,
            "gap_pct_delayed": 6.0, "current_price": 10.6, "price_source": "polygon_delayed"}


def test_authoritative_unverified_flipup_without_bar_is_dropped(monkeypatch):
    logged = _wire(monkeypatch, authoritative=True)
    now = _now()
    sn = {"price": 11.2, "price_ts": now - timedelta(seconds=5)}   # no bars at all
    out = _pass2([_flip_cand()], {"TRAX": sn}, now)
    assert out == []                                       # never-loosen: dropped by _floor
    assert "ep_rt_tick_quality_reject" in logged


def test_authoritative_unverified_flipup_with_bar_is_admitted(monkeypatch):
    logged = _wire(monkeypatch, authoritative=True)
    now = _now()
    sn = {"price": 11.2, "price_ts": now - timedelta(seconds=5),
          "minute_close": 11.1, "minute_volume": 40_000,
          "minute_ts": now - timedelta(seconds=60)}
    out = _pass2([_flip_cand()], {"TRAX": sn}, now)
    assert len(out) == 1
    assert out[0]["gap_pct"] == 12.0                       # rt decided
    assert out[0]["current_price"] == 11.2                 # §6.4 coherence (C5 fix)
    assert out[0]["price_source"] == "alpaca_sip"
    assert "ep_rt_tick_quality_reject" not in logged


def test_shadow_flipup_cohort_is_byte_identical(monkeypatch):
    # FREEZE: authority off → the decided cohort is the delayed 10% floor, exactly as today,
    # regardless of what the rt read says (the rt reading is telemetry only).
    logged = _wire(monkeypatch, authoritative=False)
    now = _now()
    sn = {"price": 11.2, "price_ts": now - timedelta(seconds=5),
          "minute_close": 11.1, "minute_volume": 40_000,
          "minute_ts": now - timedelta(seconds=60)}
    out = _pass2([_flip_cand()], {"TRAX": sn}, now)
    assert out == []                                       # delayed 6% < 10 → dropped (shadow)
    assert "ep_rt_floor_flip_up" in logged                 # …but the evidence is captured


# ── C1 fix: the 30pp Pass-2 clamp is LOUD now ──────────────────────────────────────────────

def test_pass2_clamp_emits_ep_rt_gap_clamped(monkeypatch):
    logged = _wire(monkeypatch)
    now = _now()
    sn = {"price": 14.5, "price_ts": now - timedelta(seconds=5)}   # rt +45 vs delayed +5 → Δ40pp
    cands = [{"ticker": "TRAX", "gap_pct": 5.0, "prev_close": 10.0,
              "gap_pct_delayed": 5.0, "current_price": 10.5, "price_source": "polygon_delayed"}]
    out = _pass2(cands, {"TRAX": sn}, now)
    assert "ep_rt_gap_clamped" in logged                   # "zero clamp events" is no longer vacuous
    assert "gap_pct_rt" not in cands[0]                    # clamp behavior itself unchanged


def test_universe_priced_candidate_skips_pass2_clamp(monkeypatch):
    # A Pass-0 admit (Q1-Q4-validated, possibly +95% NVVE-class) must NOT re-enter the Pass-2
    # clamp that would structurally reject it.
    logged = _wire(monkeypatch, authoritative=True)
    now = _now()
    cands = [{"ticker": "NVVE", "gap_pct": 95.0, "prev_close": 10.0,
              "current_price": 19.5, "price_source": "alpaca_sip_universe",
              "gap_pct_rt": 95.0}]
    sn = {"price": 10.2, "price_ts": now - timedelta(seconds=5)}   # would read Δ~93pp
    out = _pass2(cands, {"NVVE": sn}, now)
    assert len(out) == 1 and out[0]["gap_pct"] == 95.0
    assert "ep_rt_gap_clamped" not in logged
