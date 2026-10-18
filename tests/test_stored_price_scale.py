"""#704 - ONE answer to "did this split move the stored bars?": `db.split_row_factor` / `scale_from_split_rows` /
`stored_price_scale`, and the SQL writes that record the splits ingest's verdict.

New file (docs/testing/test_discipline.md item 1): this behaviour had no test file - the three consumers each test their OWN
policy against the shared answer (test_cb_shadow.py, test_667_unbookable_htf_fills.py, test_parabolic_short_shadow.py)
and the ingest's recording is pinned in test_split_refetch_covers_stored_history.py.

What is pinned here is the reading itself, including the BACK-FILL rule: a row written before the `adjustment_outcome`
column (outcome NULL) with adjustment_applied TRUE is read as a REAL split at the table's ratio split_from / split_to -
what every consumer assumed of the bare boolean - and a legacy phantom therefore cannot be told from a real split here
(the CB shadow's data cross-check degrades it to "sits out"; see test_cb_shadow.py).
"""
from __future__ import annotations

import asyncio
import math
from datetime import date

import pytest

from agents.market_intelligence import db

D = date


def row(split_from=1, split_to=4, *, applied=True, outcome=None, factor=None, on=D(2026, 7, 2), ticker="ZZZ"):
    return {"ticker": ticker, "execution_date": on, "split_from": split_from, "split_to": split_to,
            "adjustment_applied": applied, "adjustment_outcome": outcome, "applied_factor": factor}


# ── the reading of ONE row ───────────────────────────────────────────────────────────────
class TestSplitRowFactor:
    def test_a_row_the_ingest_has_not_handled_is_unknown(self):
        assert db.split_row_factor(row(applied=False)) is None
        assert db.split_row_factor(row(applied=False, outcome="applied", factor=0.25)) is None   # a stale verdict does not count

    @pytest.mark.parametrize("outcome", ["phantom", "skipped_no_data"])
    def test_a_phantom_or_no_data_row_moved_no_bar(self, outcome):
        assert db.split_row_factor(row(outcome=outcome)) == 1.0
        assert db.split_row_factor(row(outcome=outcome, factor=0.25)) == 1.0     # whatever a factor column holds

    @pytest.mark.parametrize("split_from,split_to,factor", [(1, 4, 0.25), (4, 1, 4.0), (3, 2, 1.5)])
    def test_an_applied_row_is_read_at_its_recorded_factor(self, split_from, split_to, factor):
        assert db.split_row_factor(row(split_from, split_to, outcome="applied", factor=factor)) == factor

    def test_the_recorded_factor_beats_the_table_ratio(self):
        assert db.split_row_factor(row(1, 4, outcome="applied", factor=0.3)) == 0.3

    @pytest.mark.parametrize("bad", [None, 0.0, -1.0, math.nan, math.inf, "x"])
    def test_an_applied_row_without_a_usable_factor_falls_back_to_the_table_ratio(self, bad):
        assert db.split_row_factor(row(1, 4, outcome="applied", factor=bad)) == 0.25

    @pytest.mark.parametrize("split_from,split_to,want", [(1, 4, 0.25), (4, 1, 4.0), (5, 2, 2.5)])
    def test_BACKFILL_a_legacy_row_applied_with_no_outcome_is_a_real_split_at_the_table_ratio(self, split_from, split_to, want):
        """The stated pre-column reading: the boolean said only "handled", every consumer took that as a real split."""
        assert db.split_row_factor(row(split_from, split_to, outcome=None)) == want

    @pytest.mark.parametrize("bad", [{"split_to": 0}, {"split_from": 0}, {"split_from": -2}, {"split_to": None}])
    def test_an_unreadable_ratio_is_unknown_not_a_guess(self, bad):
        assert db.split_row_factor({**row(), **bad}) is None

    def test_a_row_without_the_columns_at_all_is_unapplied(self):
        assert db.split_row_factor({"split_from": 1, "split_to": 4}) is None


# ── the product over a window ────────────────────────────────────────────────────────────
class TestScaleFromSplitRows:
    def test_no_split_is_one(self):
        assert db.scale_from_split_rows([]) == 1.0 and db.scale_unmoved(1.0)

    def test_the_product_is_the_plain_left_to_right_product(self):
        rows = [row(3, 7, on=D(2026, 7, 2)), row(2, 5, on=D(2026, 7, 9)), row(11, 3, on=D(2026, 7, 16))]
        want = 1.0
        for r in rows:
            want *= r["split_from"] / r["split_to"]
        assert db.scale_from_split_rows(rows) == want                              # bit-for-bit

    def test_any_unapplied_row_makes_the_whole_window_unknown(self):
        assert db.scale_from_split_rows([row(), row(applied=False, on=D(2026, 7, 9))]) is None

    def test_a_phantom_beside_a_real_split_contributes_nothing(self):
        assert db.scale_from_split_rows([row(1, 5, outcome="phantom"), row(1, 4, outcome="applied", factor=0.25,
                                                                            on=D(2026, 7, 9))]) == 0.25

    def test_a_forward_then_a_reverse_split_net_to_unmoved(self):
        """The stored series is internally consistent either way; what matters is the scale of the bar the raw price is
        compared with - and a 3:7 followed by a 7:3 puts it back (to float noise, hence `scale_unmoved`)."""
        net = db.scale_from_split_rows([row(3, 7, outcome="applied", factor=3 / 7),
                                        row(7, 3, outcome="applied", factor=7 / 3, on=D(2026, 7, 9))])
        assert db.scale_unmoved(net) and not db.scale_unmoved(0.25) and not db.scale_unmoved(4.0)


# ── the async helper + the window ────────────────────────────────────────────────────────
class _Conn:
    def __init__(self, rows=None):
        self.rows, self.fetch_calls, self.execute_calls = rows or [], [], []

    async def fetch(self, sql, *args):
        self.fetch_calls.append((" ".join(sql.split()), args))
        return self.rows

    async def execute(self, sql, *args):
        self.execute_calls.append((" ".join(sql.split()), args))
        return "UPDATE 1"


class _Pool:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        conn = self.conn

        class _Ctx:
            async def __aenter__(self):
                return conn

            async def __aexit__(self, *a):
                return False
        return _Ctx()


@pytest.fixture
def conn(monkeypatch):
    c = _Conn()

    async def _pool():
        return _Pool(c)
    monkeypatch.setattr(db, "get_pool", _pool)
    return c


class TestStoredPriceScale:
    def test_it_reads_the_half_open_window_since_exclusive_through_inclusive(self, conn):
        conn.rows = [row()]
        got = asyncio.run(db.stored_price_scale("ZZZ", D(2026, 7, 1), D(2026, 9, 18)))
        sql, args = conn.fetch_calls[0]
        assert got == 0.25                                                           # a legacy applied 1:4
        assert "execution_date > $2" in sql and "execution_date <= $3" in sql and "ticker = $1" in sql
        assert args == ("ZZZ", D(2026, 7, 1), D(2026, 9, 18))
        for col in ("adjustment_applied", "adjustment_outcome", "applied_factor"):
            assert col in sql                                                        # the ingest's verdict is what is read

    def test_no_row_is_one_and_an_unapplied_row_is_none(self, conn):
        assert asyncio.run(db.stored_price_scale("ZZZ", D(2026, 7, 1), D(2026, 9, 18))) == 1.0
        conn.rows = [row(applied=False)]
        assert asyncio.run(db.stored_price_scale("ZZZ", D(2026, 7, 1), D(2026, 9, 18))) is None

    def test_a_recorded_phantom_is_one(self, conn):
        conn.rows = [row(outcome="phantom")]
        assert asyncio.run(db.stored_price_scale("ZZZ", D(2026, 7, 1), D(2026, 9, 18))) == 1.0


class TestGetSplitDatesAfter:
    def test_the_unbounded_call_keeps_its_old_reading_and_drops_only_what_moved_no_bar(self, conn):
        conn.rows = [row(outcome="phantom", on=D(2026, 7, 2)), row(1, 4, outcome="applied", factor=0.25, on=D(2026, 7, 9)),
                     row(on=D(2026, 7, 16)), row(applied=False, on=D(2026, 7, 23)),
                     row(outcome="skipped_no_data", on=D(2026, 7, 30))]
        got = asyncio.run(db.get_split_dates_after("ZZZ", D(2026, 7, 1)))
        assert [r["execution_date"] for r in got] == [D(2026, 7, 9), D(2026, 7, 16), D(2026, 7, 23)]
        sql, args = conn.fetch_calls[0]
        assert "execution_date <=" not in sql and args == ("ZZZ", D(2026, 7, 1))     # no `through`: the pre-#704 reading

    def test_a_through_bound_is_sent_to_the_query(self, conn):
        asyncio.run(db.get_split_dates_after("ZZZ", D(2026, 7, 1), D(2026, 9, 18)))
        sql, args = conn.fetch_calls[0]
        assert "execution_date <= $3" in sql and args == ("ZZZ", D(2026, 7, 1), D(2026, 9, 18))


class TestCbBatchRows:
    def test_the_batch_reader_carries_the_ingests_verdict_columns(self, conn):
        conn.rows = [row(outcome="phantom")]
        got = asyncio.run(db.cb_get_splits_after(["ZZZ"], D(2026, 7, 1), D(2026, 9, 18)))
        assert list(got) == ["ZZZ"] and got["ZZZ"][0]["adjustment_outcome"] == "phantom"
        sql, _ = conn.fetch_calls[0]
        for col in ("adjustment_applied", "adjustment_outcome", "applied_factor"):
            assert col in sql


# ── the writes ───────────────────────────────────────────────────────────────────────────
class TestMarkAndReset:
    def test_mark_split_applied_writes_the_verdict_with_the_applied_flag(self, conn):
        asyncio.run(db.mark_split_applied("ZZZ", D(2026, 7, 2), outcome="applied", factor=0.25))
        sql, args = conn.execute_calls[0]
        assert "adjustment_applied = TRUE" in sql and "adjustment_outcome = $3" in sql and "applied_factor = $4" in sql
        assert args == ("ZZZ", D(2026, 7, 2), "applied", 0.25)

    def test_a_caller_that_names_no_outcome_writes_the_legacy_shape(self, conn):
        asyncio.run(db.mark_split_applied("ZZZ", D(2026, 7, 2)))
        assert conn.execute_calls[0][1] == ("ZZZ", D(2026, 7, 2), None, None)

    def test_an_outcome_outside_the_vocabulary_is_refused_before_any_write(self, conn):
        with pytest.raises(ValueError):
            asyncio.run(db.mark_split_applied("ZZZ", D(2026, 7, 2), outcome="applied_ish"))
        assert conn.execute_calls == []

    def test_reset_clears_the_verdict_so_a_re_apply_decides_afresh(self, conn):
        asyncio.run(db.reset_split_applied("ZZZ", D(2026, 7, 2)))
        sql, args = conn.execute_calls[0]
        assert "adjustment_applied = FALSE" in sql and "adjustment_outcome = NULL" in sql and "applied_factor = NULL" in sql
        assert args == ("ZZZ", D(2026, 7, 2))
