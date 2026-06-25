"""PERSISTENCE-TRACKING — the self-poison fix (PLAN #370 increment 2).

The bar here is the HIGHEST in the health layer: this increment exists precisely because the
rolling-baseline sweep SELF-SILENCES on a persisting break (the 200MA was null ~3 weeks; the sweep
caught it day-1 then went dark). A buggy persistence-nag would give false confidence that you'll
keep getting alerted when you won't — the exact "looked fine for weeks" failure #370 kills. So we
prove, against the EXACT self-poison data shape, that:

  (1) THE CORE FIX — a flag was raised, the rolling sweep STOPS flagging it (`_evaluate_column`
      returns None on the self-poisoned series) BUT the CONCRETE direct re-check says still-broken →
      reconcile KEEPS it open + re-alerts. We tie the concrete `_recheck_null_flag` to the SAME
      `[0.0]*3 + [1.0]*28` series that `test_persistent_null_self_silences_known_limitation` proves
      the sweep goes quiet on — that single contrast IS "the nag survives the self-poison".
  (2) RESOLVE — the column repopulates → `_recheck_null_flag` healthy → reconcile marks it resolved,
      no further nag.
  (3) CADENCE — a still-open flag does NOT re-alert twice in one ET day, but DOES the next day.

Plus the job-liveness recheck crux and reconcile's robustness (keep-open on a throwing recheck).

Mirrors test_health_checks_null_sweep.py: a `_FakeConn` routing the query shapes, then the pure
contrast tests that need no mocking at all where possible.
"""
from __future__ import annotations

from datetime import date

import pytest

from agents.market_intelligence import health_checks
from agents.market_intelligence.health_checks import (
    _evaluate_column,
    _recheck_null_flag,
    _recheck_job_liveness_flag,
    _null_flag_target_key,
    _job_flag_target_key,
    reconcile_health_flags,
)


# ════════════════════════════════════════════════════════════════════════════════════════════════
# The fake conn — routes the four query shapes increment 2 touches.
# ════════════════════════════════════════════════════════════════════════════════════════════════


class _FakeConn:
    """Routes:
      - information_schema.columns          → numeric column names (for _recheck_null_flag)
      - GROUP BY <date_col>                 → per-date {d,total,nn_<col>} rows
      - INSERT ... mi_health_open_flags     → records an upsert (and tracks state)
      - SELECT ... mi_health_open_flags     → returns the current open rows
      - UPDATE mi_health_open_flags         → mutates the tracked state
      - mi_job_runs (run-dates) / COUNT(*)  → for _recheck_job_liveness_flag

    `null_tables`: {table: (columns, date_rows)} for the null recheck path.
    `job`: {"run_dates": [...], "counts": {date: n}} for the job recheck path.
    `state`: {(check_kind, target_key): row-dict} — the persisted mi_health_open_flags rows.
    """

    def __init__(self, *, null_tables=None, job=None, state=None):
        self.null_tables = null_tables or {}
        self.job = job or {}
        self.state = state or {}
        self.executed: list[tuple] = []  # (sql, args) for every execute

    # ── fetch ────────────────────────────────────────────────────────────────────────────────────
    async def fetch(self, sql, *args):
        if "information_schema.columns" in sql:
            table = args[0]
            cols, _rows = self.null_tables[table]
            return [{"column_name": c} for c in cols]
        if "FROM mi_health_open_flags" in sql:
            check_kind = args[0]
            return [
                {"target_key": tk, **row}
                for (ck, tk), row in self.state.items()
                if ck == check_kind and row["status"] == "open"
            ]
        if "mi_job_runs" in sql:
            return [{"run_date": d} for d in self.job.get("run_dates", [])]
        # else: the per-date GROUP BY aggregation for a null table.
        for table, (_cols, rows) in self.null_tables.items():
            if f'FROM "{table}"' in sql:
                return rows
        raise AssertionError(f"unexpected fetch: {sql[:90]}")

    # ── fetchval ───────────────────────────────────────────────────────────────────────────────
    async def fetchval(self, sql, *args):
        # _new_rows_on_date: COUNT(*) FROM "table" WHERE "date_col" = $1
        if "COUNT(*)" in sql:
            run_date = args[0]
            return self.job.get("counts", {}).get(run_date, 0)
        raise AssertionError(f"unexpected fetchval: {sql[:90]}")

    # ── execute (INSERT upsert / UPDATE) ─────────────────────────────────────────────────────────
    async def execute(self, sql, *args):
        self.executed.append((sql, args))
        if "INSERT INTO mi_health_open_flags" in sql:
            check_kind, target_key, first_flagged, detail = args
            existing = self.state.get((check_kind, target_key))
            if existing is None:
                self.state[(check_kind, target_key)] = {
                    "first_flagged": first_flagged, "last_alerted": None,
                    "status": "open", "detail": detail,
                }
            else:
                # resolved→open resets first_flagged; open→open keeps it.
                if existing["status"] == "resolved":
                    existing["first_flagged"] = first_flagged
                existing["status"] = "open"
                existing["detail"] = detail
        elif "SET status = 'resolved'" in sql:
            check_kind, target_key = args
            self.state[(check_kind, target_key)]["status"] = "resolved"
        elif "SET last_alerted" in sql:
            check_kind, target_key, last_alerted = args
            self.state[(check_kind, target_key)]["last_alerted"] = last_alerted
        return "OK"


@pytest.fixture
def _captured_telegram(monkeypatch):
    sent: list[str] = []

    async def _send(text, *a, **k):
        sent.append(text)
        return True

    import agents.market_intelligence.briefing as briefing
    monkeypatch.setattr(briefing, "send_telegram_message", _send)
    return sent


@pytest.fixture
def _frozen_today(monkeypatch):
    """Pin et_today so cadence is deterministic. Returns a setter the test calls to advance days."""
    box = {"d": date(2026, 6, 25)}
    monkeypatch.setattr(health_checks, "et_today", lambda: box["d"])
    return box


# The exact self-poison series: latest null + 2 prior nulls already in the 30d baseline → 27/30 =
# 0.90 < 0.95 → `_evaluate_column` returns None (the sweep self-silences). This is the SAME shape
# test_persistent_null_self_silences_known_limitation pins.
_SELF_POISON_FRACTIONS = [0.0] * 3 + [1.0] * 28


def _regime_group_rows(latest_null: bool, prior_nulls: int = 2):
    """mi_market_regime GROUP-BY rows (one row per date, most-recent first). spy_vs_200ma null in the
    latest date when latest_null, plus `prior_nulls` more recent nulls already inside the window —
    reproducing the self-poisoned baseline shape (so the sweep would go quiet)."""
    rows = []
    rows.append({"d": "2026-06-25", "total": 1.0,
                 "nn_spy_vs_200ma": 0.0 if latest_null else 1.0})
    for i in range(30):
        nn = 0.0 if i < prior_nulls else 1.0
        rows.append({"d": f"prior-{i}", "total": 1.0, "nn_spy_vs_200ma": nn})
    return rows


# ════════════════════════════════════════════════════════════════════════════════════════════════
# THE CRUX (case 1): the sweep self-silences, but the CONCRETE recheck keeps it broken.
# ════════════════════════════════════════════════════════════════════════════════════════════════


def test_sweep_self_silences_on_the_self_poison_shape():
    """Anchor: on the SAME series the concrete recheck will be fed, the rolling-baseline evaluator
    returns None — i.e. the sweep has gone QUIET. This is the self-poison we must survive."""
    assert _evaluate_column(_SELF_POISON_FRACTIONS) is None


@pytest.mark.asyncio
async def test_concrete_recheck_says_still_broken_on_self_poison_shape(monkeypatch):
    """THE CORE FIX, half 1: the CONCRETE `_recheck_null_flag` — DECOUPLED from the baseline — returns
    True (still broken) on the EXACT data where the sweep (above) went quiet. The latest date is still
    entirely null; the direct check sees that regardless of the poisoned baseline."""
    monkeypatch.setattr(
        health_checks, "_NULL_SWEEP_TABLES", [("mi_market_regime", "regime_date")]
    )
    conn = _FakeConn(null_tables={
        "mi_market_regime": (["spy_vs_200ma"], _regime_group_rows(latest_null=True)),
    })
    still_broken = await _recheck_null_flag(conn, "mi_market_regime.spy_vs_200ma")
    assert still_broken is True, "direct re-check MUST see the latest-date null despite the poisoned baseline"


@pytest.mark.asyncio
async def test_persistence_nag_fires_after_sweep_self_silences(
    _captured_telegram, _frozen_today, monkeypatch
):
    """THE CORE FIX, end-to-end: the flag was raised earlier (an open state row exists), the rolling
    sweep now produces NO current flag for it (self-poisoned → current_flags empty), BUT the concrete
    recheck says still-broken → reconcile KEEPS it open AND re-alerts (the persistence-nag).

    This is the whole point of the increment: prove the nag SURVIVES the self-poison."""
    monkeypatch.setattr(
        health_checks, "_NULL_SWEEP_TABLES", [("mi_market_regime", "regime_date")]
    )
    # Pre-existing open flag, first seen 4 ET days ago, never re-alerted by reconcile.
    conn = _FakeConn(
        null_tables={
            # latest date STILL entirely null → the direct recheck returns still-broken...
            "mi_market_regime": (["spy_vs_200ma"], _regime_group_rows(latest_null=True)),
        },
        state={
            ("null_sweep", "mi_market_regime.spy_vs_200ma"): {
                "first_flagged": date(2026, 6, 21), "last_alerted": None,
                "status": "open", "detail": "",
            },
        },
    )

    # The sweep self-silenced → it produced NO current flag for this target.
    summary = await reconcile_health_flags(
        conn, "null_sweep", current_flags=[],
        recheck_fn=_recheck_null_flag, key_fn=_null_flag_target_key,
    )

    # KEPT OPEN + NAGGED — the alert survived the self-poison.
    assert summary["resolved"] == 0
    assert summary["nagged"] == 1
    assert summary["still_open"] == 1
    assert conn.state[("null_sweep", "mi_market_regime.spy_vs_200ma")]["status"] == "open"

    # Exactly one persistence Telegram, naming the target + days-open + since-date.
    assert len(_captured_telegram) == 1
    msg = _captured_telegram[0]
    assert "STILL BROKEN" in msg
    assert "spy_vs_200ma" in msg
    assert "5d" in msg          # first_flagged 6/21 → today 6/25 → 4 days elapsed + 1 = "5d"
    assert "2026-06-21" in msg  # the since-date

    # last_alerted was bumped to today so it won't double-nag this ET day (case 3).
    assert conn.state[("null_sweep", "mi_market_regime.spy_vs_200ma")]["last_alerted"] == date(2026, 6, 25)


# ════════════════════════════════════════════════════════════════════════════════════════════════
# Case 2 — the column repopulates → recheck healthy → resolved, no more alert.
# ════════════════════════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_repopulated_column_is_resolved(_captured_telegram, _frozen_today, monkeypatch):
    monkeypatch.setattr(
        health_checks, "_NULL_SWEEP_TABLES", [("mi_market_regime", "regime_date")]
    )
    conn = _FakeConn(
        null_tables={
            # latest date is POPULATED again → the direct recheck returns healthy.
            "mi_market_regime": (["spy_vs_200ma"], _regime_group_rows(latest_null=False)),
        },
        state={
            ("null_sweep", "mi_market_regime.spy_vs_200ma"): {
                "first_flagged": date(2026, 6, 21), "last_alerted": date(2026, 6, 24),
                "status": "open", "detail": "",
            },
        },
    )

    summary = await reconcile_health_flags(
        conn, "null_sweep", current_flags=[],
        recheck_fn=_recheck_null_flag, key_fn=_null_flag_target_key,
    )

    assert summary["resolved"] == 1
    assert summary["nagged"] == 0
    assert conn.state[("null_sweep", "mi_market_regime.spy_vs_200ma")]["status"] == "resolved"
    # No "STILL BROKEN" nag; a ✅ recovered note is the only (optional) message.
    assert not any("STILL BROKEN" in m for m in _captured_telegram)
    assert any("recovered" in m for m in _captured_telegram)


# ════════════════════════════════════════════════════════════════════════════════════════════════
# Case 3 — cadence: no double-nag same ET day; DOES nag the next day.
# ════════════════════════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_cadence_no_double_nag_same_day_then_nags_next_day(
    _captured_telegram, _frozen_today, monkeypatch
):
    monkeypatch.setattr(
        health_checks, "_NULL_SWEEP_TABLES", [("mi_market_regime", "regime_date")]
    )
    conn = _FakeConn(
        null_tables={
            "mi_market_regime": (["spy_vs_200ma"], _regime_group_rows(latest_null=True)),
        },
        state={
            ("null_sweep", "mi_market_regime.spy_vs_200ma"): {
                "first_flagged": date(2026, 6, 21), "last_alerted": None,
                "status": "open", "detail": "",
            },
        },
    )

    # Day 1 (6/25): first reconcile → nags once.
    s1 = await reconcile_health_flags(
        conn, "null_sweep", current_flags=[],
        recheck_fn=_recheck_null_flag, key_fn=_null_flag_target_key,
    )
    assert s1["nagged"] == 1
    assert len(_captured_telegram) == 1

    # Second reconcile SAME ET day → still broken but already alerted today → NO new nag.
    s2 = await reconcile_health_flags(
        conn, "null_sweep", current_flags=[],
        recheck_fn=_recheck_null_flag, key_fn=_null_flag_target_key,
    )
    assert s2["nagged"] == 0
    assert s2["still_open"] == 1          # still tracked open, just not re-alerted
    assert len(_captured_telegram) == 1   # unchanged — no spam

    # Advance one ET day → cadence elapsed → nags again.
    _frozen_today["d"] = date(2026, 6, 26)
    s3 = await reconcile_health_flags(
        conn, "null_sweep", current_flags=[],
        recheck_fn=_recheck_null_flag, key_fn=_null_flag_target_key,
    )
    assert s3["nagged"] == 1
    assert len(_captured_telegram) == 2   # exactly one more, the next day


# ════════════════════════════════════════════════════════════════════════════════════════════════
# Reconcile (a): UPSERT a current flag — sets first_flagged on insert, no nag (sweep alerts those).
# ════════════════════════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_current_flag_is_upserted_not_nagged(_captured_telegram, _frozen_today):
    conn = _FakeConn(state={})
    flag = {"table": "mi_market_regime", "column": "spy_vs_200ma",
            "baseline_rate": 1.0, "baseline_n": 30}

    summary = await reconcile_health_flags(
        conn, "null_sweep", current_flags=[flag],
        recheck_fn=_recheck_null_flag, key_fn=_null_flag_target_key,
    )

    assert summary["upserted"] == 1
    assert summary["nagged"] == 0          # the sweep day-1/2 alerts current flags; reconcile records only
    row = conn.state[("null_sweep", "mi_market_regime.spy_vs_200ma")]
    assert row["status"] == "open"
    assert row["first_flagged"] == date(2026, 6, 25)
    assert _captured_telegram == []        # no reconcile Telegram for a current flag (no double-alert)


@pytest.mark.asyncio
async def test_resolved_then_rebreak_resets_first_flagged(_captured_telegram, _frozen_today):
    """resolved→open re-break resets first_flagged (don't report an inflated days-open across the gap)."""
    conn = _FakeConn(state={
        ("null_sweep", "mi_market_regime.spy_vs_200ma"): {
            "first_flagged": date(2026, 6, 1), "last_alerted": date(2026, 6, 2),
            "status": "resolved", "detail": "",
        },
    })
    flag = {"table": "mi_market_regime", "column": "spy_vs_200ma",
            "baseline_rate": 1.0, "baseline_n": 30}

    await reconcile_health_flags(
        conn, "null_sweep", current_flags=[flag],
        recheck_fn=_recheck_null_flag, key_fn=_null_flag_target_key,
    )
    row = conn.state[("null_sweep", "mi_market_regime.spy_vs_200ma")]
    assert row["status"] == "open"
    assert row["first_flagged"] == date(2026, 6, 25), "re-break after resolve resets first_flagged"


# ════════════════════════════════════════════════════════════════════════════════════════════════
# Robustness — a throwing recheck KEEPS-OPEN (never silently resolves a real break).
# ════════════════════════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_throwing_recheck_keeps_open(_captured_telegram, _frozen_today):
    conn = _FakeConn(state={
        ("null_sweep", "mi_market_regime.spy_vs_200ma"): {
            "first_flagged": date(2026, 6, 21), "last_alerted": date(2026, 6, 25),
            "status": "open", "detail": "",
        },
    })

    async def _boom(_conn, _target):
        raise RuntimeError("recheck blew up")

    summary = await reconcile_health_flags(
        conn, "null_sweep", current_flags=[],
        recheck_fn=_boom, key_fn=_null_flag_target_key,
    )

    # A broken re-check must NOT resolve — keep-open + record the error.
    assert summary["resolved"] == 0
    assert summary["still_open"] == 1
    assert conn.state[("null_sweep", "mi_market_regime.spy_vs_200ma")]["status"] == "open"
    assert any("error" in e for e in summary["errors"])


@pytest.mark.asyncio
async def test_reconcile_scoped_by_check_kind(_captured_telegram, _frozen_today, monkeypatch):
    """A null_sweep reconcile must NOT touch a job_liveness open row (scoping by check_kind)."""
    monkeypatch.setattr(
        health_checks, "_NULL_SWEEP_TABLES", [("mi_market_regime", "regime_date")]
    )
    conn = _FakeConn(
        null_tables={
            "mi_market_regime": (["spy_vs_200ma"], _regime_group_rows(latest_null=False)),
        },
        state={
            # a job_liveness row that must be left entirely alone by a null_sweep reconcile
            ("job_liveness", "theme_synthesis:mi_theme_candidates_shadow"): {
                "first_flagged": date(2026, 6, 20), "last_alerted": None,
                "status": "open", "detail": "",
            },
        },
    )

    await reconcile_health_flags(
        conn, "null_sweep", current_flags=[],
        recheck_fn=_recheck_null_flag, key_fn=_null_flag_target_key,
    )
    # The job_liveness row is untouched.
    assert conn.state[("job_liveness", "theme_synthesis:mi_theme_candidates_shadow")]["status"] == "open"


# ════════════════════════════════════════════════════════════════════════════════════════════════
# The job-liveness recheck crux — direct, decoupled from the K-consecutive cadence gate.
# ════════════════════════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_job_recheck_still_broken_when_latest_run_empty(monkeypatch):
    """Direct job recheck: the latest successful run-date STILL produced 0 rows → still broken,
    regardless of how the K-window cadence has aged."""
    monkeypatch.setattr(health_checks, "_is_trading_day", lambda d: True)
    conn = _FakeConn(job={
        "run_dates": [date(2026, 6, 25)],
        "counts": {date(2026, 6, 25): 0},   # latest successful run produced nothing
    })
    still_broken = await _recheck_job_liveness_flag(
        conn, "theme_synthesis:mi_theme_candidates_shadow"
    )
    assert still_broken is True


@pytest.mark.asyncio
async def test_job_recheck_healthy_when_latest_run_produced(monkeypatch):
    monkeypatch.setattr(health_checks, "_is_trading_day", lambda d: True)
    conn = _FakeConn(job={
        "run_dates": [date(2026, 6, 25)],
        "counts": {date(2026, 6, 25): 12},  # latest successful run produced rows → healthy
    })
    still_broken = await _recheck_job_liveness_flag(
        conn, "theme_synthesis:mi_theme_candidates_shadow"
    )
    assert still_broken is False
