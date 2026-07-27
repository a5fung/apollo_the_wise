"""#498 TQS Stage 1 — Tape Quality Score SHADOW annotation (docs/design/tape_quality_score.md).

Pins, in order:
  • the labelled-6 reproduction — fixtures engineered to the design §3 component table
    (FCEL/SHAZ/CRML clean · GLND 3 spikes 1H/2R bmr2≈2.1 junk · HTCO×2 4 spikes 2H/2R bmr2≈8 junk);
  • rule R1's arms individually (rev-driven junk, spike-count junk, bmr2 junk, the watch band,
    the lone-legit-event-bar clean tolerance);
  • the guardrails: `unknown` (<15 live bars) is NEVER junk and renders "unseasoned" (never
    "clean"); no lookahead (alert-day/after bars can't move the score; a last-in-window spike
    falls back to close-position only);
  • probe↔module parity — the production port must be byte-faithful to the VALIDATED
    scripts/probes/_tape_quality_step0.py math;
  • format_tape_line / tape_sparkline rendering;
  • THE HARD STAGE-1 CONSTRAINT (telemetry-only): the annotator records tape_* fields WITHOUT
    touching tier/score (byte-identical results with TQS on vs off), the pinned UPDATE SQL
    touches ONLY tape_* columns, and static pins prove the ep_detector call site sits
    DOWNSTREAM of every grade decision.
"""
from __future__ import annotations

import asyncio
import copy
import importlib
import sys
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

from tests.conftest import make_mock_pool

import agents.market_intelligence.tape_quality as tq
from agents.market_intelligence.tape_quality import (
    _MIN_LIVE_BARS,
    _SPARK_BLOCKS,
    _WIN,
    annotate_ep_alerts_tape_quality,
    format_tape_line,
    tape_quality,
    tape_sparkline,
)


def _run(coro):
    return asyncio.run(coro)


# ─── Bar fixture builders ─────────────────────────────────────────────────────────────────
# Engineered so the R1 components come out EXACTLY at the design §3 labelled-table values
# (spike/held/rev counts, bmr2 ballpark) — each fixture's own test asserts the components, so
# a drifted fixture fails loudly rather than silently testing the wrong shape.

_D0 = date(2026, 6, 1)
_ALERT = _D0 + timedelta(days=_WIN)  # bars occupy d0..d19; the alert day is d20


def _d(i: int) -> date:
    return _D0 + timedelta(days=i)


def _bar(d, *, h, l, c, o=None, v=1_000_000):
    return {"trade_date": d, "open_price": o if o is not None else c,
            "high_price": h, "low_price": l, "close": c, "volume": v}


def _flat(i: int, close: float, ntr_pct: float) -> dict:
    """A baseline bar with NTR exactly `ntr_pct` (range centred on `close`)."""
    rng = close * ntr_pct / 100
    return _bar(_d(i), h=close + rng / 2, l=close - rng / 2, c=close)


def _fcel_bars() -> list[dict]:
    """FCEL-like CLEAN at high ADR (design §3: 0 spikes, bmr2 ~1.4, adr ~15 — volatility LEVEL
    alone never grades junk; the discriminator is the reversal count)."""
    bars = [_flat(i, 100, 14) for i in range(20)]
    bars[6] = _flat(6, 100, 20)    # largest NTR — below the 2x-median spike line (28)
    bars[13] = _flat(13, 100, 21)
    return bars


def _shaz_bars() -> list[dict]:
    bars = [_flat(i, 100, 11) for i in range(20)]
    bars[6] = _flat(6, 100, 16)
    bars[13] = _flat(13, 100, 17)
    return bars


def _crml_bars() -> list[dict]:
    bars = [_flat(i, 100, 12) for i in range(20)]
    bars[6] = _flat(6, 100, 18)
    bars[13] = _flat(13, 100, 19)
    return bars


def _glnd_bars() -> list[dict]:
    """GLND-like JUNK via the REVERSAL arm alone (design §3: 3 spikes, 1 held / 2 reversed,
    bmr2 ≈ 2.1 — i.e. junk fires on rev>=2 while spike_ct<4 and bmr2<3)."""
    bars = [_flat(i, 100, 10) for i in range(4)]
    # HELD spike: closes at its high, next 2 closes keep the level (giveback 0.23 < 0.60)
    bars.append(_bar(_d(4), o=100.0, h=126.6, l=100.0, c=126.0))       # NTR 21.1
    bars += [_flat(i, 120, 10) for i in range(5, 10)]
    # REVERSED spike (up, weak close): close_pos 0.05 < 0.70
    bars.append(_bar(_d(10), o=120.0, h=145.0, l=119.8, c=121.0))      # NTR 20.8
    bars += [_flat(i, 121, 10) for i in range(11, 15)]
    # REVERSED spike (down, snaps back): closes at its low, next 2 closes recover ~91% of range
    bars.append(_bar(_d(15), o=121.0, h=121.2, l=96.0, c=97.0))        # NTR 26.0
    bars += [_flat(i, 120, 10) for i in range(16, 20)]
    return bars


def _htco_bars() -> list[dict]:
    """HTCO-like JUNK, all three arms (design §3: 4 spikes, 2 held / 2 reversed, bmr2 ~8)."""
    bars = [_flat(i, 100, 5) for i in range(3)]
    bars.append(_bar(_d(3), o=100.0, h=166.7, l=100.0, c=166.0))       # HELD, NTR 40.2
    bars += [_flat(i, 160, 5) for i in range(4, 7)]
    bars.append(_bar(_d(7), o=160.0, h=224.0, l=159.5, c=160.5))       # REV, NTR 40.2
    bars += [_flat(i, 160, 5) for i in range(8, 11)]
    bars.append(_bar(_d(11), o=160.0, h=266.7, l=160.0, c=266.0))      # HELD, NTR 40.1
    bars += [_flat(i, 250, 5) for i in range(12, 15)]
    bars.append(_bar(_d(15), o=250.0, h=350.0, l=249.0, c=251.0))      # REV, NTR 40.2
    bars += [_flat(i, 250, 5) for i in range(16, 20)]
    return bars


def _one_rev_bars() -> list[dict]:
    """Exactly one reversed spike → WATCH (rev == 1)."""
    bars = [_flat(i, 100, 10) for i in range(10)]
    bars.append(_bar(_d(10), o=100.0, h=125.0, l=99.8, c=101.0))       # REV, NTR 25.0
    bars += [_flat(i, 101, 10) for i in range(11, 20)]
    return bars


def _one_held_bars() -> list[dict]:
    """One BIG bar that held (a legit event bar — earnings / prior EP) → stays CLEAN
    (the operator caveat: don't filter out what makes an EP an EP)."""
    bars = [_flat(i, 100, 10) for i in range(10)]
    bars.append(_bar(_d(10), o=100.0, h=140.0, l=100.0, c=139.0))      # HELD, NTR 28.8
    bars += [_flat(i, 130, 10) for i in range(11, 20)]                  # keeps the level
    return bars


def _two_held_bars() -> list[dict]:
    """Two held spikes, modest magnitude (bmr2 2.2 < 2.5) → WATCH via spike_ct in {2,3}."""
    bars = [_flat(i, 100, 10) for i in range(5)]
    bars.append(_bar(_d(5), o=100.0, h=128.0, l=100.0, c=127.0))       # HELD, NTR 22.0
    bars += [_flat(i, 120, 10) for i in range(6, 12)]
    bars.append(_bar(_d(12), o=120.0, h=153.6, l=120.0, c=152.6))      # HELD, NTR 22.0
    bars += [_flat(i, 145, 10) for i in range(13, 20)]
    return bars


def _bmr2_junk_bars() -> list[dict]:
    """Two HELD spikes but huge (2nd-largest 3.5x median) → JUNK via the bmr2 arm alone
    (outlier magnitude trips even without reversals — but never on ONE lone event bar)."""
    bars = [_flat(i, 100, 10) for i in range(5)]
    bars.append(_bar(_d(5), o=100.0, h=154.0, l=100.0, c=153.5))       # HELD, NTR 35.2
    bars += [_flat(i, 150, 10) for i in range(6, 12)]
    bars.append(_bar(_d(12), o=150.0, h=231.0, l=150.0, c=230.0))      # HELD, NTR 35.2
    bars += [_flat(i, 225, 10) for i in range(13, 20)]
    return bars


def _four_held_bars() -> list[dict]:
    """Four spikes, ALL held, modest magnitude (bmr2 2.2) → JUNK via spike_ct >= 4 alone
    (big bars that REPEAT are junk even when each individually held)."""
    bars = [_flat(i, 100, 10) for i in range(4)]
    bars.append(_bar(_d(4), o=100.0, h=128.0, l=100.0, c=127.0))       # HELD, NTR 22.0
    bars += [_flat(i, 120, 10) for i in range(5, 8)]
    bars.append(_bar(_d(8), o=120.0, h=153.6, l=120.0, c=152.6))       # HELD, NTR 22.0
    bars += [_flat(i, 145, 10) for i in range(9, 12)]
    bars.append(_bar(_d(12), o=145.0, h=185.6, l=145.0, c=184.5))      # HELD, NTR 22.0
    bars += [_flat(i, 175, 10) for i in range(13, 16)]
    bars.append(_bar(_d(16), o=175.0, h=224.0, l=175.0, c=222.7))      # HELD, NTR 22.0
    bars += [_flat(i, 215, 10) for i in range(17, 20)]
    return bars


_ALL_FIXTURES = {
    "fcel": _fcel_bars, "shaz": _shaz_bars, "crml": _crml_bars,
    "glnd": _glnd_bars, "htco": _htco_bars,
    "one_rev": _one_rev_bars, "one_held": _one_held_bars, "two_held": _two_held_bars,
    "bmr2_junk": _bmr2_junk_bars, "four_held": _four_held_bars,
}


# ─── The labelled-6 (design §3, operator ground truth) ────────────────────────────────────

def test_labelled_fcel_clean_at_high_adr():
    q = tape_quality(_fcel_bars(), _ALERT)
    assert q["tier"] == "tape_clean"
    assert q["spike_ct"] == 0 and q["held"] == 0 and q["rev"] == 0
    assert 1.3 < q["bmr2"] < 1.6            # design table: 1.4
    assert q["adr"] > 14                    # high volatility LEVEL, still clean
    assert q["n"] == 20


def test_labelled_shaz_and_crml_clean():
    for bars in (_shaz_bars(), _crml_bars()):
        q = tape_quality(bars, _ALERT)
        assert q["tier"] == "tape_clean"
        assert q["spike_ct"] == 0
        assert q["bmr2"] < 2.5              # design table: 1.4–1.7


def test_labelled_glnd_junk_via_reversals():
    q = tape_quality(_glnd_bars(), _ALERT)
    assert q["tier"] == "tape_junk"
    assert q["spike_ct"] == 3
    assert q["held"] == 1 and q["rev"] == 2  # design table: 3 (1/2)
    assert 2.0 < q["bmr2"] < 2.5             # design table: 2.1 — junk from rev>=2 ALONE
    assert abs(q["ntr_med"] - 10.0) < 1e-9


def test_labelled_htco_junk_both_alert_days():
    """HTCO alerted twice (5/11 + 5/12 in the labelled set) — the same wide-and-loose tape
    grades junk on both alert days."""
    bars = _htco_bars()
    for alert in (_ALERT, _ALERT + timedelta(days=1)):
        q = tape_quality(bars, alert)
        assert q["tier"] == "tape_junk"
        assert q["spike_ct"] == 4
        assert q["held"] == 2 and q["rev"] == 2  # design table: 4 (2/2)
        assert q["bmr2"] > 3.0                    # design table: 8.2


# ─── Rule R1 arms individually ────────────────────────────────────────────────────────────

def test_single_reversed_spike_is_watch():
    q = tape_quality(_one_rev_bars(), _ALERT)
    assert q["tier"] == "tape_watch"
    assert q["spike_ct"] == 1 and q["rev"] == 1


def test_single_held_event_bar_stays_clean():
    """The operator caveat + the bmr2 (2nd-largest) design: ONE legit event bar that holds
    (earnings / prior EP) must not cost the name its clean grade."""
    q = tape_quality(_one_held_bars(), _ALERT)
    assert q["tier"] == "tape_clean"
    assert q["spike_ct"] == 1 and q["held"] == 1 and q["rev"] == 0
    assert q["bmr2"] < 2.5


def test_two_held_spikes_are_watch():
    q = tape_quality(_two_held_bars(), _ALERT)
    assert q["tier"] == "tape_watch"
    assert q["spike_ct"] == 2 and q["held"] == 2 and q["rev"] == 0
    assert q["bmr2"] < 2.5


def test_bmr2_arm_junks_even_when_spikes_held():
    q = tape_quality(_bmr2_junk_bars(), _ALERT)
    assert q["tier"] == "tape_junk"
    assert q["rev"] == 0 and q["spike_ct"] == 2   # neither of the other junk arms fired
    assert q["bmr2"] >= 3.0


def test_spike_count_arm_junks_even_when_all_held():
    q = tape_quality(_four_held_bars(), _ALERT)
    assert q["tier"] == "tape_junk"
    assert q["spike_ct"] == 4 and q["held"] == 4 and q["rev"] == 0
    assert q["bmr2"] < 3.0                        # junk from spike_ct>=4 ALONE


# ─── Guardrail A: unknown = "unseasoned", NEVER junk ──────────────────────────────────────

def test_under_15_bars_is_unknown_even_when_whippy():
    """14 live bars containing reversal spikes → unknown (never junk — no penalty for missing
    data); the base-age/IPO gates own the trade decision, not TQS."""
    q = tape_quality(_glnd_bars()[:14], _ALERT)
    assert q == {"tier": "unknown", "n": 14}


def test_dead_volume_bars_do_not_count_as_live():
    """20 bars but 6 are volume=0 (halt/dead rows) → only 14 LIVE → unknown. Dead rows still
    occupy window slots (the validated probe's window semantics)."""
    bars = _fcel_bars()
    for i in range(6):
        bars[i]["volume"] = 0
    q = tape_quality(bars, _ALERT)
    assert q == {"tier": "unknown", "n": 14}


def test_exactly_15_live_bars_is_computable():
    bars = _fcel_bars()[-_MIN_LIVE_BARS:]
    q = tape_quality(bars, _ALERT)
    assert q["tier"] == "tape_clean"
    assert q["n"] == 15


# ─── Guardrail B: no lookahead ────────────────────────────────────────────────────────────

def test_alert_day_and_after_bars_never_move_the_score():
    """A monster bar ON the alert day (the EP's own thrust) or after it must be invisible —
    the window is strictly pre-alert by construction."""
    base = _glnd_bars()
    with_future = base + [
        _bar(_ALERT, o=100.0, h=1000.0, l=10.0, c=500.0),
        _bar(_ALERT + timedelta(days=1), o=500.0, h=2000.0, l=5.0, c=100.0),
    ]
    assert tape_quality(with_future, _ALERT) == tape_quality(base, _ALERT)


def test_last_in_window_spike_falls_back_to_close_position_only():
    """A spike on the LAST pre-alert bar has no in-window next closes — the give-back look
    must NOT peek at the alert day: verdict comes from close position alone."""
    held = [_flat(i, 100, 10) for i in range(19)]
    held.append(_bar(_d(19), o=100.0, h=126.6, l=100.0, c=126.0))   # closes at its high
    q_held = tape_quality(held, _ALERT)
    assert q_held["held"] == 1 and q_held["rev"] == 0
    assert q_held["tier"] == "tape_clean"                            # lone held event bar

    rev = [_flat(i, 100, 10) for i in range(19)]
    rev.append(_bar(_d(19), o=100.0, h=125.0, l=99.8, c=101.0))      # closes weak
    q_rev = tape_quality(rev, _ALERT)
    assert q_rev["rev"] == 1
    assert q_rev["tier"] == "tape_watch"


# ─── Probe ↔ module parity (the port is byte-faithful to the VALIDATED math) ──────────────

def test_module_matches_validated_probe_on_all_fixtures():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    probe = importlib.import_module("scripts.probes._tape_quality_step0")
    for name, mk in _ALL_FIXTURES.items():
        bars = mk()
        assert tape_quality(bars, _ALERT) == probe.tape_quality(bars, _ALERT), name
    # the unknown + lookahead variants too
    assert tape_quality(_glnd_bars()[:14], _ALERT) == probe.tape_quality(_glnd_bars()[:14], _ALERT)
    extra = _htco_bars() + [_bar(_ALERT, o=1.0, h=999.0, l=1.0, c=500.0)]
    assert tape_quality(extra, _ALERT) == probe.tape_quality(extra, _ALERT)


# ─── format_tape_line ─────────────────────────────────────────────────────────────────────

def test_format_line_clean():
    line = format_tape_line(tape_quality(_fcel_bars(), _ALERT))
    assert line.startswith("TAPE:")
    assert "clean" in line
    assert "0 spikes ·" in line       # no "(0 held/0 rev)" breakdown on a clean tape
    assert "held" not in line
    assert "2nd-widest 1.4×" in line
    assert "ADR" in line


def test_format_line_junk_counts():
    line = format_tape_line(tape_quality(_glnd_bars(), _ALERT))
    assert "junk" in line
    assert "3 spikes (1 held/2 rev)" in line
    assert "2nd-widest 2.1×" in line


def test_format_line_watch_singular_spike():
    line = format_tape_line(tape_quality(_one_rev_bars(), _ALERT))
    assert "watch" in line
    assert "1 spike (0 held/1 rev)" in line
    assert "1 spikes" not in line


def test_format_line_unknown_renders_unseasoned_never_clean_or_junk():
    line = format_tape_line({"tier": "unknown", "n": 9})
    assert "unseasoned" in line
    assert "9 live bars" in line
    assert "clean" not in line     # guardrail A: unknown must NEVER read as clean
    assert "junk" not in line      # …and never as a penalty either


def test_format_line_empty_inputs():
    assert format_tape_line(None) == ""
    assert format_tape_line({}) == ""


# ─── tape_sparkline ───────────────────────────────────────────────────────────────────────

def test_sparkline_ramp_min_to_max():
    bars = [_flat(i, 100, 1 + i) for i in range(20)]    # NTR 1% → 20% ramp
    s = tape_sparkline(bars, _ALERT)
    assert len(s) == 20
    assert s[0] == _SPARK_BLOCKS[0] and s[-1] == _SPARK_BLOCKS[-1]
    assert set(s) <= set(_SPARK_BLOCKS)


def test_sparkline_flat_window_and_lengths():
    assert tape_sparkline([_flat(i, 100, 10) for i in range(20)], _ALERT) == _SPARK_BLOCKS[0] * 20
    assert len(tape_sparkline([_flat(i, 100, 10) for i in range(5)], _ALERT)) == 5
    assert tape_sparkline([], _ALERT) == ""


def test_sparkline_excludes_alert_day():
    base = [_flat(i, 100, 5 + i % 7) for i in range(20)]
    with_alert_day = base + [_bar(_ALERT, o=100.0, h=400.0, l=50.0, c=200.0)]
    assert tape_sparkline(with_alert_day, _ALERT) == tape_sparkline(base, _ALERT)


# ─── THE HARD STAGE-1 CONSTRAINT — telemetry-only, mechanically pinned ────────────────────

def _mk_results():
    return [
        {"ticker": "JUNKY", "alert_date": _ALERT, "ep_score": 74.0, "score_tier": "HIGH",
         "gap_pct": 12.5, "fire_axes": ["catalyst"], "judge_rationale": "8-K",
         "grade_engine_authority": "judge", "baseline_floor_tier": "MODERATE",
         "score_breakdown": {"gap": 25, "catalyst": 25}},
        {"ticker": "CLEANY", "alert_date": _ALERT, "ep_score": 55.0, "score_tier": "MODERATE",
         "gap_pct": 9.0, "grade_engine_authority": "floor"},
    ]


def _patch_annotator(monkeypatch, bars_by):
    """Wire the annotator to a mock pool + fixture bars; returns the mock conn (its
    `.execute` AsyncMock receives the tape UPDATEs)."""
    pool, conn = make_mock_pool()
    conn.execute = AsyncMock()

    async def _fake_pool():
        return pool

    async def _fake_bars(_conn, ticker, _alert_date, days=380):
        return bars_by[ticker]

    monkeypatch.setattr(tq, "get_pool", _fake_pool)
    monkeypatch.setattr(tq, "get_tape_bars_asof", _fake_bars)
    return conn


def test_annotator_records_fields_without_touching_tier_or_score(monkeypatch):
    """THE #498 Stage-1 pin: with TQS ON vs OFF, the graded alert dict is BYTE-IDENTICAL apart
    from the added display-only 'tape_quality' + 'vol_profile' keys — even when the tape
    verdict is junk on a HIGH. score_tier / ep_score / authority / every other field
    untouched. (The vol-profile Slice-1 sibling rides the same loop under the same
    telemetry-only contract — see tests/test_vol_profile.py for its own pins.)"""
    _patch_annotator(monkeypatch, {"JUNKY": _glnd_bars(), "CLEANY": _fcel_bars()})

    results = _mk_results()
    before = copy.deepcopy(results)          # == the TQS-OFF outcome
    _run(annotate_ep_alerts_tape_quality(results))

    for r_after, r_before in zip(results, before):
        stripped = {k: v for k, v in r_after.items()
                    if k not in ("tape_quality", "vol_profile")}
        assert stripped == r_before          # byte-identical minus the annotations
        assert r_after["score_tier"] == r_before["score_tier"]
        assert r_after["ep_score"] == r_before["ep_score"]
    assert results[0]["tape_quality"]["tier"] == "tape_junk"   # junk verdict, HIGH untouched
    assert results[1]["tape_quality"]["tier"] == "tape_clean"
    assert len(results[0]["tape_quality"]["sparkline"]) == 20
    # The vol sibling annotated too (20 fixture bars < 50 → honest 'unseasoned' shape).
    assert results[0]["vol_profile"]["hist_n"] == 20
    assert "r5_50" not in results[0]["vol_profile"]


def test_annotator_writes_only_the_pinned_tape_sql(monkeypatch):
    """Every statement the annotator loop issues is one of the two PINNED telemetry updates
    (tape_* / vol_*) — nothing else can reach the row from here."""
    from agents.market_intelligence.db import (
        EP_ALERT_TAPE_UPDATE_SQL, EP_ALERT_VOL_UPDATE_SQL,
    )
    conn = _patch_annotator(monkeypatch, {"JUNKY": _glnd_bars(), "CLEANY": _fcel_bars()})

    _run(annotate_ep_alerts_tape_quality(_mk_results()))

    assert conn.execute.await_count == 4     # tape + vol, per candidate
    tape_calls = [c for c in conn.execute.await_args_list
                  if c.args[0] == EP_ALERT_TAPE_UPDATE_SQL]
    vol_calls = [c for c in conn.execute.await_args_list
                 if c.args[0] == EP_ALERT_VOL_UPDATE_SQL]
    assert len(tape_calls) == 2 and len(vol_calls) == 2
    assert len(tape_calls) + len(vol_calls) == conn.execute.await_count
    junky = tape_calls[0].args
    assert junky[1] == "JUNKY" and junky[2] == _ALERT
    assert junky[3] == "tape_junk"
    assert junky[4] == 3 and junky[5] == 1 and junky[6] == 2   # spike_ct / held / rev


def test_tape_update_sql_touches_only_tape_columns():
    """Mechanical proof of the telemetry-only property at the WRITE: every SET assignment
    targets a tape_* column; no grading/sizing column is even mentioned in the statement."""
    from agents.market_intelligence.db import EP_ALERT_TAPE_UPDATE_SQL as sql
    set_clause = sql.split("SET", 1)[1].split("WHERE", 1)[0]
    assigns = [a.strip() for a in set_clause.split(",") if a.strip()]
    assert len(assigns) == 6
    for a in assigns:
        col = a.split("=", 1)[0].strip()
        assert col.startswith("tape_"), f"non-tape column in the TQS update: {col}"
    for forbidden in ("score_tier", "ep_score", "judge_tier", "grade_engine_authority",
                      "confidence_multiplier", "setup_class", "fire_"):
        assert forbidden not in sql


def test_annotator_persists_unknown_with_null_components(monkeypatch):
    """'unknown' rows persist tier='unknown' + NULL components — post-hoc distinguishable from
    an all-NULL row (annotator never ran). The vol sibling mirrors the shape: hist_n with
    NULL metric components on an unseasoned (<50-bar) name."""
    from agents.market_intelligence.db import (
        EP_ALERT_TAPE_UPDATE_SQL, EP_ALERT_VOL_UPDATE_SQL,
    )
    conn = _patch_annotator(monkeypatch, {"IPO": _fcel_bars()[:10]})

    results = [{"ticker": "IPO", "alert_date": _ALERT, "ep_score": 70.0, "score_tier": "HIGH"}]
    _run(annotate_ep_alerts_tape_quality(results))

    tape_args = next(c.args for c in conn.execute.await_args_list
                     if c.args[0] == EP_ALERT_TAPE_UPDATE_SQL)
    assert tape_args[3] == "unknown"
    assert tape_args[4] is None and tape_args[5] is None \
        and tape_args[6] is None and tape_args[7] is None
    assert results[0]["tape_quality"]["tier"] == "unknown"
    vol_args = next(c.args for c in conn.execute.await_args_list
                    if c.args[0] == EP_ALERT_VOL_UPDATE_SQL)
    assert vol_args[3] == 10                                   # vol_hist_n persists
    assert vol_args[4] is None and vol_args[5] is None and vol_args[6] is None


def test_annotator_isolates_per_candidate_failures(monkeypatch):
    """One bad ticker (bars fetch blows up) can't suppress the sibling annotations, never
    raises, and is COUNTED via the tape_quality_shadow_failed audit event."""
    _patch_annotator(monkeypatch, {"CLEANY": _fcel_bars()})

    async def _boom_then_ok(_conn, ticker, _alert_date, days=380):
        if ticker == "JUNKY":
            raise RuntimeError("history fetch failed")
        return _fcel_bars()
    monkeypatch.setattr(tq, "get_tape_bars_asof", _boom_then_ok)
    audit = AsyncMock()
    monkeypatch.setattr(tq, "log_audit_event", audit)

    results = _mk_results()
    _run(annotate_ep_alerts_tape_quality(results))   # must not raise

    assert "tape_quality" not in results[0]          # failed candidate: no annotation
    assert results[1]["tape_quality"]["tier"] == "tape_clean"
    assert audit.await_count == 1
    assert audit.await_args.args[0] == "tape_quality_shadow_failed"
    # Vol sibling: no bars for the failed candidate → skipped (the fetch failure was
    # already audited once above — no double-count); the healthy sibling still annotated.
    assert "vol_profile" not in results[0]
    assert results[1]["vol_profile"]["hist_n"] == 20


def test_annotator_db_first_no_line_when_row_write_fails(monkeypatch):
    """DB-first (the fire_axes discipline): if the row write fails, r is NOT annotated — the
    alert never renders a TAPE (or VOL) line the row lacks."""
    import agents.market_intelligence.vol_profile as vpm
    conn = _patch_annotator(monkeypatch, {"JUNKY": _glnd_bars(), "CLEANY": _fcel_bars()})
    conn.execute = AsyncMock(side_effect=RuntimeError("db down"))
    monkeypatch.setattr(tq, "log_audit_event", AsyncMock())
    monkeypatch.setattr(vpm, "log_audit_event", AsyncMock())

    results = _mk_results()
    _run(annotate_ep_alerts_tape_quality(results))
    assert all("tape_quality" not in r for r in results)
    assert all("vol_profile" not in r for r in results)


def test_annotator_empty_results_never_touches_the_pool(monkeypatch):
    pool_call = AsyncMock()
    monkeypatch.setattr(tq, "get_pool", pool_call)
    _run(annotate_ep_alerts_tape_quality([]))
    assert pool_call.await_count == 0


# ─── Static pins — call-site placement + module blast radius ──────────────────────────────

def test_ep_detector_call_site_is_downstream_of_every_grade_decision():
    """The telemetry-only property BY PLACEMENT: the annotate call is the LAST post-scan block
    in run_ep_scan — textually after the alert insert, the judge write, the composite-authority
    resolution, and the grade-decision emit, and immediately before the final return. TQS runs
    only once every decision has settled, so it cannot feed any of them."""
    import agents.market_intelligence.ep_detector as epd
    src = open(epd.__file__).read()
    call = src.rindex("annotate_ep_alerts_tape_quality")
    assert call > src.rindex("insert_ep_alert")
    assert call > src.rindex("update_ep_alert_judge_result")
    assert call > src.rindex("_emit_grade_decision")
    assert call > src.rindex("resolve_composite_tier")
    assert call > src.rindex("update_ep_alert_setup_class")
    assert call < src.rindex("return results")


def test_tape_quality_module_never_touches_decision_paths():
    """Static blast-radius pin (mirrors test_structure_axis_shadow's): the TQS module must
    never reference grade/judge/entry internals or assign the graded fields."""
    src = open(tq.__file__).read()
    forbidden = (
        "submit_trade_entry", "entry_pipeline", "grade_holistic", "assemble_judge_inputs",
        "resolve_composite_tier", "update_ep_alert_judge_result", "ep_threshold",
        'r["score_tier"] =', "r['score_tier'] =", 'r["ep_score"] =', "r['ep_score'] =",
        "import ep_detector", "from agents.market_intelligence.ep_detector",
    )
    for token in forbidden:
        assert token not in src, f"tape_quality.py must never reference {token!r}"


# ─── Alert surface (send_ep_alert renders the annotation, guarded) ────────────────────────

def _send_alert_capture(ep):
    from agents.market_intelligence import briefing
    captured = {}

    async def _cap(text, *a, **k):
        captured["text"] = text
        return True

    with patch.object(briefing, "send_telegram_message", new=AsyncMock(side_effect=_cap)):
        asyncio.run(briefing.send_ep_alert(ep))
    return captured["text"]


def test_ep_alert_renders_tape_line_and_sparkline():
    tqs = tape_quality(_glnd_bars(), _ALERT)
    tqs["sparkline"] = tape_sparkline(_glnd_bars(), _ALERT)
    ep = {"ticker": "GLND", "score_tier": "HIGH", "gap_pct": 11.0, "ep_score": 78,
          "catalyst_quality": "strong", "rel_volume": 3.0, "tape_quality": tqs}
    text = _send_alert_capture(ep)
    assert "TAPE: *junk*" in text
    assert "3 spikes (1 held/2 rev)" in text
    assert f"`{tqs['sparkline']}`" in text


def test_ep_alert_without_annotation_has_no_tape_line():
    ep = {"ticker": "BARE", "score_tier": "HIGH", "gap_pct": 8.0, "ep_score": 72,
          "catalyst_quality": "strong", "rel_volume": 2.0}
    text = _send_alert_capture(ep)
    assert "TAPE:" not in text
