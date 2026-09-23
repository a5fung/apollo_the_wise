"""NULL-RATE DRIFT sweep — the generic 200MA-catch (PLAN #370, operator 6/24).

The bar here is HIGHER than usual: a BUGGY guard gives FALSE CONFIDENCE that you'll be alerted
when you won't. So we prove, mock-free, that:
  (1) a column non-null across ~30 prior dates but NULL in the latest date IS flagged
      — and we use the exact `mi_market_regime.spy_vs_200ma` shape, since #370's DoD is literally
      "the 200MA-null would have alerted DAY-1";
  (2) a column legitimately null ~half the time is NOT flagged (noise calibration — self-excludes
      via the ≥95% baseline gate);
  (3) an always-null column is NOT flagged (never met the populated bar);
  (4) the sweep survives an empty / erroring table without crashing.

Mirrors `test_l2_persistence_dedup.py`: the PURE decision (`_evaluate_column`) is tested directly
first with zero mocking, then one integration test drives the real SQL-shaped path via a fake conn.
"""
from __future__ import annotations

import pytest

from agents.market_intelligence import health_checks
from agents.market_intelligence.health_checks import (
    _evaluate_column,
    _fractions_for_column,
    run_null_rate_sweep,
)


# ── Pure decision: _evaluate_column (no mocking) ──────────────────────────────


def test_silently_broken_column_is_flagged():
    # The 200MA shape: full (1.0) across 30 prior dates, NULL (0.0) in the latest date.
    # per_date_fractions is MOST-RECENT-FIRST, so the latest is index 0.
    fractions = [0.0] + [1.0] * 30
    verdict = _evaluate_column(fractions)
    assert verdict is not None, "a normally-populated column gone null in latest date MUST flag"
    assert verdict["baseline_rate"] == 1.0
    assert verdict["baseline_n"] == 30


def test_near_perfect_baseline_still_flags():
    # 98% populated baseline (one historical gap) + latest null → still over the 0.95 bar → flags.
    # This is the realistic 200MA case (occasional historical holiday-edge null).
    baseline = [1.0] * 49 + [0.0]  # 49/50 = 0.98
    fractions = [0.0] + baseline
    verdict = _evaluate_column(fractions)
    assert verdict is not None
    assert verdict["baseline_rate"] == 0.98


def test_legit_half_null_column_not_flagged():
    # A column legitimately null ~half the time (e.g. rel_volume / theme_score): baseline ~50%
    # never clears the 0.95 gate → NEVER a candidate, even with the latest date null. Noise
    # calibration: this is the false-positive class the guard must NOT raise.
    baseline = [1.0, 0.0] * 15  # 30 dates, 50% non-null
    fractions = [0.0] + baseline
    assert _evaluate_column(fractions) is None


def test_always_null_column_not_flagged():
    # Always null → never met the "normally populated" bar → not a silent failure, just sparse.
    fractions = [0.0] * 31
    assert _evaluate_column(fractions) is None


def test_latest_still_populated_not_flagged():
    # Nothing broke — latest date still has data.
    fractions = [1.0] * 31
    assert _evaluate_column(fractions) is None


def test_partial_null_latest_not_flagged():
    # Conservative trigger: a PARTIALLY-null latest date (some rows populated) does NOT fire.
    # Partial-break detection is a deferred refinement.
    fractions = [0.5] + [1.0] * 30
    assert _evaluate_column(fractions) is None


def test_too_few_dates_not_flagged():
    # < 10 baseline dates → not enough history to judge "normally populated".
    fractions = [0.0] + [1.0] * 5
    assert _evaluate_column(fractions) is None


def test_persistent_null_self_silences_known_limitation():
    # KNOWN LIMITATION (pinned in code so it can't silently change): once a null has PERSISTED into
    # the baseline window it stops flagging. 3 null dates already in the baseline → 27/30 = 0.90 <
    # 0.95 → None. The sweep fires day-1/day-2 then self-silences; re-alerting on a persistent null
    # is the DEFERRED hard-check/heartbeat increment, not this one. Operator-scoping call.
    fractions = [0.0] * 3 + [1.0] * 28  # latest null + 2 prior nulls already in the 30d baseline
    assert _evaluate_column(fractions) is None


def test_fractions_for_column_extraction():
    # The per-date fraction extractor turns GROUP-BY rows (total + per-col non-null count)
    # into the most-recent-first fraction series _evaluate_column consumes.
    date_rows = [
        {"d": "2026-06-24", "total": 4.0, "nn_x": 4.0},   # latest: full
        {"d": "2026-06-23", "total": 4.0, "nn_x": 4.0},
        {"d": "2026-06-22", "total": 4.0, "nn_x": 2.0},   # half
    ]
    assert _fractions_for_column(date_rows, "x") == [1.0, 1.0, 0.5]


# ── Integration: real SQL-shaped path via a fake conn ─────────────────────────


class _FakeConn:
    """Stand-in for an asyncpg conn. Routes the two query shapes the sweep issues:
      - information_schema.columns → returns the numeric column names for the table
      - GROUP BY <date_col>        → returns per-date {d, total, nn_<col>...} rows
    Per-table behaviour is supplied by `tables`: {table_name: (columns, date_rows)}.
    A table whose value is the sentinel "ERROR" raises, to exercise the try/except robustness.
    """

    def __init__(self, tables: dict):
        self._tables = tables

    async def fetch(self, sql, *args):
        if "information_schema.columns" in sql:
            table = args[0]
            entry = self._tables.get(table)
            if entry == "ERROR":
                raise RuntimeError(f"boom on {table}")
            cols, _rows = entry
            return [{"column_name": c} for c in cols]
        # else: the GROUP-BY aggregation query. Identify the table from the FROM clause.
        for table, entry in self._tables.items():
            if f'FROM "{table}"' in sql:
                if entry == "ERROR":
                    raise RuntimeError(f"boom on {table}")
                _cols, rows = entry
                return rows
        raise AssertionError(f"unexpected query: {sql[:80]}")


def _regime_rows(latest_200ma_null: bool):
    """30 prior dates fully populated + a latest date. spy_vs_200ma goes null in the latest row
    when latest_200ma_null — the exact 200MA silent-failure shape (one row per date)."""
    rows = []
    # latest date first
    rows.append({
        "d": f"2026-06-24",
        "total": 1.0,
        "nn_spy_vs_200ma": 0.0 if latest_200ma_null else 1.0,
        "nn_spy_vs_50ma": 1.0,
    })
    for i in range(30):
        rows.append({
            "d": f"prior-{i}",
            "total": 1.0,
            "nn_spy_vs_200ma": 1.0,
            "nn_spy_vs_50ma": 1.0,
        })
    return rows


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
def _captured_audit(monkeypatch):
    events: list[tuple] = []

    async def _audit(event_type, summary, detail=""):
        events.append((event_type, summary, detail))

    monkeypatch.setattr(health_checks, "log_audit_event", _audit)
    return events


@pytest.mark.asyncio
async def test_200ma_null_fires_telegram_and_audit(_captured_telegram, _captured_audit, monkeypatch):
    # Only sweep the regime table for this case (focus the assertion on the DoD scenario).
    monkeypatch.setattr(
        health_checks, "_NULL_SWEEP_TABLES", [("mi_market_regime", "regime_date")]
    )
    conn = _FakeConn({
        "mi_market_regime": (["spy_vs_200ma", "spy_vs_50ma"], _regime_rows(latest_200ma_null=True)),
    })

    summary = await run_null_rate_sweep(conn)

    # The flag fired on exactly spy_vs_200ma (the 200MA catch), not spy_vs_50ma.
    flagged = {(f["table"], f["column"]) for f in summary["flags"]}
    assert ("mi_market_regime", "spy_vs_200ma") in flagged
    assert ("mi_market_regime", "spy_vs_50ma") not in flagged
    assert len(summary["flags"]) == 1

    # ONE grouped Telegram, naming the broken column.
    assert len(_captured_telegram) == 1
    assert "spy_vs_200ma" in _captured_telegram[0]
    assert "SILENT-NULL" in _captured_telegram[0]

    # Audit row written with the flagged event type.
    assert any(e[0] == "health_null_sweep_flagged" for e in _captured_audit)


@pytest.mark.asyncio
async def test_clean_run_no_telegram_audit_only(_captured_telegram, _captured_audit, monkeypatch):
    # spy_vs_200ma still populated in the latest date → nothing broke → NO Telegram, audit-only.
    monkeypatch.setattr(
        health_checks, "_NULL_SWEEP_TABLES", [("mi_market_regime", "regime_date")]
    )
    conn = _FakeConn({
        "mi_market_regime": (["spy_vs_200ma", "spy_vs_50ma"], _regime_rows(latest_200ma_null=False)),
    })

    summary = await run_null_rate_sweep(conn)

    assert summary["flags"] == []
    assert _captured_telegram == []  # Telegram reserved for real failures
    assert any(e[0] == "health_null_sweep_clean" for e in _captured_audit)


@pytest.mark.asyncio
async def test_erroring_table_does_not_kill_sweep(_captured_telegram, _captured_audit, monkeypatch):
    # One table raises; a healthy table after it still gets swept and its real flag still fires.
    monkeypatch.setattr(
        health_checks,
        "_NULL_SWEEP_TABLES",
        [("mi_bad_table", "bad_date"), ("mi_market_regime", "regime_date")],
    )
    conn = _FakeConn({
        "mi_bad_table": "ERROR",
        "mi_market_regime": (["spy_vs_200ma", "spy_vs_50ma"], _regime_rows(latest_200ma_null=True)),
    })

    summary = await run_null_rate_sweep(conn)

    # The sweep survived: the bad table is recorded as an error, the good table still flagged.
    assert summary["tables_scanned"] == 1  # only the healthy table completed
    assert any(err.get("table") == "mi_bad_table" for err in summary["errors"])
    assert any(f["column"] == "spy_vs_200ma" for f in summary["flags"])


def _multirow_scores_rows():
    """mi_stock_scores shape: MANY rows per date. rs_composite is broken (null in latest date);
    sector_pct is legitimately sparse (~50% populated every date) and must NOT flag."""
    rows = []
    # latest date: 9700 rows, rs_composite went entirely null, sparse col half-populated
    rows.append({"d": "2026-06-24", "total": 9700.0, "nn_rs_composite": 0.0, "nn_sparse": 4800.0})
    for i in range(30):
        rows.append({
            "d": f"prior-{i}",
            "total": 9700.0,
            "nn_rs_composite": 9700.0,   # fully populated historically
            "nn_sparse": 4850.0,         # ~50% every date → never clears the 0.95 gate
        })
    return rows


@pytest.mark.asyncio
async def test_multirow_table_flags_broken_not_sparse(_captured_telegram, _captured_audit, monkeypatch):
    # The novel/hard part: per-date aggregation over a MULTI-ROW table (~9,700 rows/day).
    # rs_composite (broken) flags; the legitimately-sparse column self-excludes via the 95% gate.
    monkeypatch.setattr(
        health_checks, "_NULL_SWEEP_TABLES", [("mi_stock_scores", "score_date")]
    )
    conn = _FakeConn({
        "mi_stock_scores": (["rs_composite", "sparse"], _multirow_scores_rows()),
    })

    summary = await run_null_rate_sweep(conn)

    flagged = {f["column"] for f in summary["flags"]}
    assert "rs_composite" in flagged          # silently broken on a multi-row table → flags
    assert "sparse" not in flagged            # legit ~50%-null → self-excludes (noise calibration)
    assert len(summary["flags"]) == 1


@pytest.mark.asyncio
async def test_empty_table_no_crash(_captured_telegram, _captured_audit, monkeypatch):
    # A table with columns but NO rows (empty / never written) must not crash — and must not flag
    # (no per-date history → can't judge; the "0 rows today" case is the DEFERRED job-liveness sweep).
    monkeypatch.setattr(
        health_checks, "_NULL_SWEEP_TABLES", [("mi_market_regime", "regime_date")]
    )
    conn = _FakeConn({
        "mi_market_regime": (["spy_vs_200ma"], []),  # no date rows at all
    })

    summary = await run_null_rate_sweep(conn)

    assert summary["flags"] == []
    assert summary["tables_scanned"] == 1
    assert _captured_telegram == []
