"""PLAN #216 — repair for double/multi-encoded JSONB columns (`scripts/_216_jsonb_repair.py`).

WHY THIS EXISTS. `db.py`'s jsonb codec auto-json.dumps()es every jsonb bind param; several
write-path call sites ALSO json.dumps()ed before binding `$N::jsonb`, so the column holds
a JSON *string* containing JSON text instead of a real object/array (measured on prod
2026-08-17, ~4,300 rows across 9 tables — see PLAN.md #216). This file pins the REPAIR
script's behavior: a double-encoded value gets un-wrapped to the real object/array, a
genuinely-string jsonb value (scalar or non-JSON text) is left untouched, multi-level
encoding fully unwraps, dry-run never mutates, and the dump is written before any UPDATE.
"""
import inspect
import json
import re
from pathlib import Path

import pytest

from scripts import _216_jsonb_repair as repair_mod
from scripts._216_jsonb_repair import (
    _fully_decode, _build_repair_plan, build_plans, run_with_conn, _apply_repairs,
)


# ─── _fully_decode — pure decision logic ───────────────────────────────────────────────


def test_double_encoded_object_is_repaired():
    original = {"rs_composite": 100.0}
    # Simulates the real bug: json.dumps() at the call site + json.dumps() again by the
    # codec encoder -> jsonb_typeof='string' -> col::text gives this exact text back.
    raw_text = json.dumps(json.dumps(original))
    decoded, levels = _fully_decode(raw_text)
    assert decoded == original
    assert levels == 2


def test_double_encoded_array_is_repaired():
    original = ["EP_HIGH", "9M_DAY2"]
    raw_text = json.dumps(json.dumps(original))
    decoded, levels = _fully_decode(raw_text)
    assert decoded == original
    assert levels == 2


def test_legit_string_value_is_left_alone():
    """A jsonb column can legitimately hold a plain string. It must not be touched."""
    raw_text = json.dumps("some free-text note")
    decoded, levels = _fully_decode(raw_text)
    assert decoded is None
    assert levels == 0


def test_string_that_decodes_to_a_scalar_is_left_alone():
    """The decoded string parses as JSON but yields a NUMBER, not an object/array — spec
    says leave it alone (only object/array is a repair candidate)."""
    raw_text = json.dumps("42")
    decoded, levels = _fully_decode(raw_text)
    assert decoded is None


def test_string_that_decodes_to_a_bool_is_left_alone():
    raw_text = json.dumps("true")
    decoded, levels = _fully_decode(raw_text)
    assert decoded is None


def test_multi_level_encoding_fully_decodes():
    """Handles more than one extra layer, not just exactly two."""
    original = {"a": [1, 2, 3]}
    raw_text = json.dumps(json.dumps(json.dumps(original)))  # triple-encoded
    decoded, levels = _fully_decode(raw_text)
    assert decoded == original
    assert levels == 3


def test_non_parsing_garbage_is_left_alone():
    raw_text = json.dumps("not valid json at all {{{")
    decoded, levels = _fully_decode(raw_text)
    assert decoded is None


def test_malformed_top_level_text_does_not_raise():
    """Defensive: even if jsonb_typeof lied (shouldn't happen), a garbage col_text must
    never crash the sweep — it just gets left alone."""
    decoded, levels = _fully_decode("{not even valid json")
    assert decoded is None
    assert levels == 0


# ─── _build_repair_plan — classification over a batch of rows ─────────────────────────


def test_build_repair_plan_splits_repair_and_leave_alone():
    rows = [
        {"id": 1, "col_text": json.dumps(json.dumps({"a": 1}))},   # repair
        {"id": 2, "col_text": json.dumps("legit free text")},       # leave alone
    ]
    plan = _build_repair_plan("mi_signal_outcomes", "detail", ["id"], rows)
    assert plan["string_typed"] == 2
    assert len(plan["repairs"]) == 1
    assert len(plan["left_alone"]) == 1
    assert plan["repairs"][0]["pk"] == {"id": 1}
    assert plan["repairs"][0]["decoded"] == {"a": 1}
    assert plan["left_alone"][0]["pk"] == {"id": 2}


# ─── Fake conn — routes by SQL substring, mirrors tests/conftest.make_mock_pool's role ──


class _FakeConn:
    """Minimal asyncpg-conn stand-in. Routes .fetch() by recognizable SQL substrings
    (identifiers are f-string-interpolated in this script, not bound params, so routing
    on text is the natural seam) and records every .execute() call for assertions."""

    def __init__(self, jsonb_columns, pk_by_table, rows_by_table_col):
        self.jsonb_columns = jsonb_columns
        self.pk_by_table = pk_by_table
        self.rows_by_table_col = rows_by_table_col
        self.executed = []
        self.tx_entered = 0

    async def fetch(self, sql, *args):
        if "information_schema.columns" in sql:
            return [{"table_name": t, "column_name": c} for t, c in self.jsonb_columns]
        if "table_constraints" in sql:
            table = args[0]
            return [{"column_name": c} for c in self.pk_by_table.get(table, [])]
        if "jsonb_typeof" in sql:
            table = re.search(r'FROM "([^"]+)"', sql).group(1)
            column = re.search(r'"([^"]+)"::text', sql).group(1)
            return list(self.rows_by_table_col.get((table, column), []))
        raise AssertionError(f"unrouted fetch: {sql}")

    async def execute(self, sql, *args):
        self.executed.append((sql, args))

    def transaction(self):
        outer = self

        class _Tx:
            async def __aenter__(self_):
                outer.tx_entered += 1
                return self_

            async def __aexit__(self_, *exc):
                return False

        return _Tx()


def _conn_with_one_double_encoded_row():
    original = {"rs_composite": 100.0}
    raw_text = json.dumps(json.dumps(original))
    return _FakeConn(
        jsonb_columns=[("mi_signal_outcomes", "detail")],
        pk_by_table={"mi_signal_outcomes": ["id"]},
        rows_by_table_col={("mi_signal_outcomes", "detail"): [{"id": 7, "col_text": raw_text}]},
    ), original


# ─── run_with_conn — orchestration: dump-before-mutate, dry-run no-ops, apply repairs ──


@pytest.mark.asyncio
async def test_dry_run_mutates_nothing(tmp_path):
    conn, _ = _conn_with_one_double_encoded_row()
    result = await run_with_conn(conn, apply=False, output_dir=tmp_path)
    assert conn.executed == []
    assert conn.tx_entered == 0
    # The dump is still written on a dry run (a reviewable preview) — but nothing mutated.
    assert Path(result["dump_path"]).exists()
    dumped = json.loads(Path(result["dump_path"]).read_text())
    assert dumped["mode"] == "dryrun"
    assert dumped["tables"][0]["repair_count"] == 1


@pytest.mark.asyncio
async def test_apply_repairs_the_double_encoded_row(tmp_path):
    conn, original = _conn_with_one_double_encoded_row()
    await run_with_conn(conn, apply=True, output_dir=tmp_path)
    assert len(conn.executed) == 1
    sql, params = conn.executed[0]
    assert '::jsonb' in sql
    jsonb_param = params[0]
    # Must be bound as a PLAIN str (asyncpg's default jsonb codec passes it through
    # unencoded) equal to json.dumps(original) EXACTLY ONCE — binding the dict itself, or
    # double-dumps-ing it, would reintroduce the very bug this script repairs.
    assert isinstance(jsonb_param, str)
    assert jsonb_param == json.dumps(original)
    assert json.loads(jsonb_param) == original
    assert params[1:] == (7,)  # the pk value, id=7
    assert conn.tx_entered == 1


@pytest.mark.asyncio
async def test_dump_is_written_before_any_mutation(tmp_path, monkeypatch):
    """If _apply_repairs blows up, the dump must already exist — reversibility can't
    depend on the mutation succeeding."""
    conn, _ = _conn_with_one_double_encoded_row()

    async def _boom(conn, plans):
        raise RuntimeError("simulated mutation failure")

    monkeypatch.setattr("scripts._216_jsonb_repair._apply_repairs", _boom)
    with pytest.raises(RuntimeError):
        await run_with_conn(conn, apply=True, output_dir=tmp_path)
    dumps = list(tmp_path.glob("apply_*.json"))
    assert len(dumps) == 1
    payload = json.loads(dumps[0].read_text())
    assert payload["tables"][0]["repair_count"] == 1


@pytest.mark.asyncio
async def test_legit_string_value_survives_a_real_apply_run(tmp_path):
    """A leave-alone row must not appear in conn.executed at all."""
    conn = _FakeConn(
        jsonb_columns=[("mi_weekly_watchlists", "sources")],
        pk_by_table={"mi_weekly_watchlists": ["week_ending", "ticker"]},
        rows_by_table_col={("mi_weekly_watchlists", "sources"): [
            {"week_ending": "2026-08-14", "ticker": "TEST", "col_text": json.dumps("legit note")},
        ]},
    )
    await run_with_conn(conn, apply=True, output_dir=tmp_path)
    assert conn.executed == []


@pytest.mark.asyncio
async def test_table_with_no_primary_key_is_skipped_not_guessed():
    conn = _FakeConn(
        jsonb_columns=[("mi_no_pk_table", "blob")],
        pk_by_table={},  # no PK registered -> _primary_key_columns returns []
        rows_by_table_col={},
    )
    plans = await build_plans(conn)
    assert len(plans) == 1
    assert plans[0]["skipped_no_pk"] is True
    assert plans[0]["repairs"] == []


@pytest.mark.asyncio
async def test_composite_primary_key_binds_both_columns_in_order():
    original = ["EP_HIGH"]
    raw_text = json.dumps(json.dumps(original))
    conn = _FakeConn(
        jsonb_columns=[("mi_weekly_watchlists", "sources")],
        pk_by_table={"mi_weekly_watchlists": ["week_ending", "ticker"]},
        rows_by_table_col={("mi_weekly_watchlists", "sources"): [
            {"week_ending": "2026-08-14", "ticker": "TEST", "col_text": raw_text},
        ]},
    )
    await run_with_conn(conn, apply=True, output_dir=Path("/tmp"))
    sql, params = conn.executed[0]
    assert params[1:] == ("2026-08-14", "TEST")


@pytest.mark.asyncio
async def test_mi_live_trades_is_never_mutated_even_if_string_typed(tmp_path):
    """THE LINE: `mi_live_trades` is live trade state. Even if discovery finds a
    string-typed row there (today it never does — measured clean on prod — but a future
    write-path regression could put one there), this script must NEVER touch it. Unlike
    every other table, `mi_live_trades` here DOES carry a real double-encoded row in
    rows_by_table_col — a positive proof: the row exists and is classified as repairable,
    yet the exclusion must still stop it from ever reaching conn.execute()."""
    original = {"realized_r": 1.4}
    raw_text = json.dumps(json.dumps(original))
    conn = _FakeConn(
        jsonb_columns=[("mi_live_trades", "exits"), ("mi_signal_outcomes", "detail")],
        pk_by_table={"mi_live_trades": ["id"], "mi_signal_outcomes": ["id"]},
        rows_by_table_col={
            ("mi_live_trades", "exits"): [{"id": 99, "col_text": raw_text}],
            ("mi_signal_outcomes", "detail"): [
                {"id": 1, "col_text": json.dumps(json.dumps({"a": 1}))},
            ],
        },
    )
    result = await run_with_conn(conn, apply=True, output_dir=tmp_path)
    live_trades_plans = [p for p in result["plans"] if p["table"] == "mi_live_trades"]
    assert len(live_trades_plans) == 1
    assert live_trades_plans[0]["skipped_excluded"] is True
    assert live_trades_plans[0]["repairs"] == []  # excluded BEFORE classification, not after
    assert all("mi_live_trades" not in sql for sql, _ in conn.executed)
    # The other table's genuine repair still happens — exclusion is table-scoped, not global.
    assert len(conn.executed) == 1
    assert "mi_signal_outcomes" in conn.executed[0][0]


def test_discovery_excludes_views_not_just_base_tables():
    """A VIEW with a jsonb column must not be treated as a repair target — it has no PK of
    its own and a jsonb_typeof scan over it would run the view's whole query for nothing."""
    src = inspect.getsource(repair_mod._discover_jsonb_columns)
    assert "BASE TABLE" in src


@pytest.mark.asyncio
async def test_idempotent_second_pass_sees_nothing_left_to_repair():
    """After a repair, jsonb_typeof(col) is no longer 'string' — a second run's SELECT
    (simulated here by an empty rows_by_table_col) must find zero rows, confirming the
    WHERE clause itself is what makes this idempotent, not extra bookkeeping."""
    conn = _FakeConn(
        jsonb_columns=[("mi_signal_outcomes", "detail")],
        pk_by_table={"mi_signal_outcomes": ["id"]},
        rows_by_table_col={("mi_signal_outcomes", "detail"): []},  # already clean
    )
    result = await run_with_conn(conn, apply=True, output_dir=Path("/tmp"))
    assert conn.executed == []
    assert result["plans"] == []  # clean columns produce no report noise
