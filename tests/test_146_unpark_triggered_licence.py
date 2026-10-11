"""#146 UNPARKED (operator ruling 2026-10-11) - a breakout may read TRIGGERED from a TIGHTENING-or-better label
without first reaching COILED, and every raw TRIGGERED row says which path licensed it.

THE RULE (exactly arm B of docs/analysis/146_detection_page_2026-10-11.md): a breakout reads TRIGGERED when
  (shipped path) COILED today, or a COILED stored label in the 5-calendar-day window, OR
  (new path)    any TIGHTENING / COILED / TRIGGERED stored label in that window - held labels counting.
The breakout leg (close over the base's highest close on >= 1.5x the base's recent volume) is untouched.

THE STAMP (his reason: track performance per path, and tell where too many breakouts come from):
  mi_flag_candidates.triggered_from  'coiled' | 'tightening' | 'retrigger'  - on a RAW TRIGGERED read only.
A HELD TRIGGERED row (yesterday's TRIGGERED kept over a lower raw read) was licensed by NOTHING today, so it is
NULL there, and every bucket SELECT in htf.md filters held_from_stage IS NULL.

NOT MONEY: no order / entry / sizing / safeguard path reads these labels. That is an ABSENCE, proved by grep and
captured in scripts/probes/_146_unpark/money_grep_*.out (a test of it would be a source pin, and the source-pin
baseline only goes down); the execution container also never loads flag_detector (preflight 5n).
"""
from __future__ import annotations

import re
from datetime import timedelta
from unittest.mock import AsyncMock

import pytest

from agents.market_intelligence import db
from agents.market_intelligence import flag_detector as fd
from tests.conftest import make_mock_pool
from tests.test_htf_criteria import _htf_rows, _row


# -- fixture: a qualified flag whose LAST bar is a breakout (close over the base's highest close) ------------------

def _breakout_rows(vol=2_000_000, bump=1.06):
    rows = _htf_rows(runup_ratio=2.0, flag_depth=0.10, n_flag=8)
    last = rows[-1]
    fp = last["close"]
    rows.append(_row(last["trade_date"] + timedelta(days=1), fp, fp * bump * 1.01, fp * 0.99, fp * bump, vol))
    return rows


def _score(stages, **kw):
    return fd.compute_flag_metrics(kw.pop("rows", None) or _breakout_rows(), ticker="TST", recent_stages=stages, **kw)


# -- 1. the new path: TIGHTENING / TRIGGERED labels license a breakout ------------------------------------------------

def test_a_tightening_label_in_the_window_licenses_the_breakout():
    out = _score(["TIGHTENING"])
    assert out["stage"] == "TRIGGERED" and out["held_from_stage"] is None
    assert out["triggered_from"] == "tightening"
    assert out["breakout_close"] is not None and out["breakout_volume_ratio"] >= fd._BREAKOUT_VOL_RATIO


def test_a_prior_triggered_label_alone_licenses_a_retrigger():
    out = _score(["TRIGGERED"])
    assert (out["stage"], out["triggered_from"]) == ("TRIGGERED", "retrigger")


def test_the_licence_is_membership_in_the_window_not_the_last_label():
    # the page's arm B: 9 of the 101 extras had a real TIGHTENING 2-4 sessions back followed by WATCH /
    # INVALIDATED days. The stored window is a LIST of every row, so this is `in`, not `[-1] ==`.
    for window in (["TIGHTENING", "WATCH"], ["TIGHTENING", "INVALIDATED", "WATCH"],
                   ["WATCH", "TIGHTENING", "unqualified"], ["TIGHTENING", "WATCH", "WATCH", "WATCH", "WATCH"]):
        out = _score(window)
        assert (out["stage"], out["triggered_from"]) == ("TRIGGERED", "tightening"), window


def test_only_the_last_five_stored_labels_count():
    out = _score(["TIGHTENING"] + ["WATCH"] * 5)
    assert out["stage"] == "WATCH" and out["triggered_from"] is None


# -- 2. precedence: coiled > tightening > retrigger (the page's section 2 definition) ---------------------------------

@pytest.mark.parametrize("window,bucket", [
    (["COILED"], "coiled"),
    (["TIGHTENING", "COILED"], "coiled"),
    (["COILED", "TIGHTENING"], "coiled"),
    (["TRIGGERED", "COILED"], "coiled"),
    (["TIGHTENING"], "tightening"),
    (["TIGHTENING", "TRIGGERED"], "tightening"),      # 'only a prior TRIGGERED' means NO tightening label either
    (["TRIGGERED", "TIGHTENING"], "tightening"),
    (["TRIGGERED"], "retrigger"),
    (["WATCH", "TRIGGERED", "WATCH"], "retrigger"),
])
def test_the_bucket_is_the_strongest_licence_in_the_window(window, bucket):
    assert fd.trigger_licence(False, window) == bucket
    assert _score(window)["triggered_from"] == bucket


def test_coiled_today_is_the_coiled_bucket_whatever_the_window_holds():
    for window in (None, [], ["WATCH"], ["TIGHTENING"], ["TRIGGERED"], ["TIGHTENING", "COILED"]):
        assert fd.trigger_licence(True, window) == "coiled", window


# -- 3. nothing else moved: the shipped COILED path, the breakout leg, WATCH-only windows --------------------------

def test_the_shipped_coiled_path_is_unchanged():
    out = _score(["COILED"])
    assert (out["stage"], out["triggered_from"]) == ("TRIGGERED", "coiled")
    assert out["reason"].startswith("close_19.08>base_high_close_18.00 vol_2.50x")


@pytest.mark.parametrize("window", [None, [], ["WATCH"], ["unqualified"], ["INVALIDATED"], ["WATCH", "INVALIDATED"]])
def test_a_window_with_no_tightening_or_better_label_licenses_nothing(window):
    out = _score(window)
    assert out["stage"] == "WATCH" and out["triggered_from"] is None
    assert out["breakout_close"] is None and out["breakout_volume_ratio"] is None
    assert fd.trigger_licence(False, window) is None


def test_the_volume_leg_is_untouched():
    out = _score(["TIGHTENING"], rows=_breakout_rows(vol=900_000))          # 1.13x, under the 1.5x leg
    assert out["stage"] != "TRIGGERED" and out["triggered_from"] is None


def test_the_close_over_the_base_leg_is_untouched():
    rows = _breakout_rows(bump=0.99)                                          # closes inside the base
    out = _score(["TIGHTENING"], rows=rows)
    assert out["stage"] != "TRIGGERED" and out["triggered_from"] is None


def test_a_non_breakout_bar_is_never_triggered_whatever_the_window():
    rows = _htf_rows(runup_ratio=2.0, flag_depth=0.10, n_flag=8)             # today is an ordinary flag bar
    for window in (["TIGHTENING"], ["TRIGGERED"], ["COILED"]):
        out = fd.compute_flag_metrics(rows, ticker="TST", recent_stages=window)
        assert out["stage"] != "TRIGGERED" and out["triggered_from"] is None, window


def test_a_held_triggered_row_carries_no_licence_because_nothing_licensed_it_today():
    out = _score([], yesterday_stage="TRIGGERED")                            # raw read WATCH, yesterday's TRIGGERED held
    assert (out["stage"], out["held_from_stage"]) == ("TRIGGERED", "WATCH")
    assert out["triggered_from"] is None
    assert out["breakout_close"] is None


def test_a_raw_triggered_read_is_never_held_and_carries_a_licence():
    out = _score(["TIGHTENING"], yesterday_stage="COILED", yesterday_was_held=False)
    assert (out["stage"], out["held_from_stage"], out["triggered_from"]) == ("TRIGGERED", None, "tightening")


# -- 4. the one-line revert restores the shipped rule exactly --------------------------------------------------------

def test_dropping_the_two_new_entries_restores_the_shipped_rule(monkeypatch):
    monkeypatch.setattr(fd, "_TRIGGER_LICENCE", (("COILED", "coiled"),))
    for window in (["TIGHTENING"], ["TRIGGERED"], ["TIGHTENING", "TRIGGERED"], ["WATCH"], []):
        out = _score(window)
        assert out["stage"] == "WATCH" and out["triggered_from"] is None, window
    out = _score(["COILED"])
    assert (out["stage"], out["triggered_from"]) == ("TRIGGERED", "coiled")
    assert fd.trigger_licence(True, []) == "coiled"                           # the same-day half is never behind the flag


def test_the_vocabulary_is_closed_and_the_precedence_is_the_declared_order():
    assert fd._TRIGGER_LICENCE == (("COILED", "coiled"), ("TIGHTENING", "tightening"), ("TRIGGERED", "retrigger"))
    assert fd.TRIGGERED_FROM_BUCKETS == ("coiled", "tightening", "retrigger")
    seen = {fd.trigger_licence(c, w) for c in (True, False) for w in (None, [], ["WATCH"], ["COILED"], ["TIGHTENING"],
                                                                     ["TRIGGERED"], ["TIGHTENING", "TRIGGERED"])}
    assert seen == {None, *fd.TRIGGERED_FROM_BUCKETS}


# -- 5. persistence -----------------------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_insert_flag_candidate_writes_the_stamp_in_its_own_column(monkeypatch):
    pool, conn = make_mock_pool()
    conn.execute = AsyncMock()
    monkeypatch.setattr(db, "get_pool", AsyncMock(return_value=pool))
    metrics = _score(["TIGHTENING"])
    await db.insert_flag_candidate(metrics)
    sql, *args = conn.execute.call_args.args
    cols = re.search(r"INSERT INTO mi_flag_candidates\s*\((.*?)\)\s*VALUES", sql, re.S).group(1)
    names = [c.strip() for c in cols.split(",")]
    placeholders = re.search(r"VALUES\s*\((.*?)\)\s*ON CONFLICT", sql, re.S).group(1)
    n_values = len([p for p in placeholders.split(",") if p.strip()])
    assert len(names) == n_values == len(args), "columns, placeholders and arguments must line up"
    assert args[names.index("triggered_from")] == "tightening"
    assert "triggered_from = EXCLUDED.triggered_from" in re.sub(r"\s+", " ", sql.split("DO UPDATE SET")[1])


@pytest.mark.asyncio
async def test_the_schema_step_declares_the_column_and_backfills_it_exactly_once(monkeypatch):
    """Runs the REAL `initialize_schema` against a connection that records every statement it is sent, and reads
    what was sent: the column is in CREATE TABLE (fresh databases), and on an existing table the guarded block adds
    it AND labels the already-stored raw TRIGGERED rows 'coiled' in that same exactly-once step - every one of them
    was licensed by the shipped path, so from then on a raw TRIGGERED row with a NULL stamp is a defect."""
    pool, conn = make_mock_pool()
    sent = []

    async def _execute(q, *a, **kw):
        sent.append(q)

    conn.execute = _execute
    conn.executemany = AsyncMock()
    for m in ("fetch", "fetchval", "fetchrow"):
        setattr(conn, m, AsyncMock(return_value=None))
    monkeypatch.setattr(db, "get_pool", AsyncMock(return_value=pool))
    await db.initialize_schema()

    ddl = next(q for q in sent if "CREATE TABLE IF NOT EXISTS mi_flag_candidates" in q)
    create = ddl[ddl.index("CREATE TABLE IF NOT EXISTS mi_flag_candidates"):]
    create = create[:create.index(");")]
    assert re.search(r"^\s+triggered_from\s+TEXT,", create, re.M), "declared in CREATE TABLE (fresh databases)"
    guard = ddl[ddl.index("DO $$ BEGIN", ddl.index("undercut_after_breakout BOOLEAN;")):]
    guard = guard[:guard.index("END $$;")]
    assert "column_name = 'triggered_from'" in guard and "IF NOT EXISTS" in guard
    assert guard.index("ADD COLUMN triggered_from TEXT") < guard.index("UPDATE mi_flag_candidates")
    assert re.search(r"SET triggered_from = 'coiled'\s+WHERE stage = 'TRIGGERED'\s+AND held_from_stage IS NULL", guard)
    assert guard.index("UPDATE mi_flag_candidates") < guard.index("END IF;"), "the backfill is INSIDE the guard"
    assert "ALTER TABLE mi_flag_candidates ADD COLUMN IF NOT EXISTS triggered_from TEXT;" in ddl


@pytest.mark.asyncio
async def test_the_history_reader_selects_the_stamp(monkeypatch):
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[])
    monkeypatch.setattr(db, "get_pool", AsyncMock(return_value=pool))
    await db.get_ticker_flag_history("TST", 14)
    assert "triggered_from" in conn.fetch.call_args.args[0]


# -- 6. every site that demotes a TRIGGERED row to `unqualified` clears the stamp -----------------------------------

class _World:
    def __init__(self):
        self.inserted = []


def _triggered_row(ticker):
    return {"ticker": ticker, "stage": "TRIGGERED", "triggered_from": "tightening", "held_from_stage": None,
            "runup_pct": 1.30, "pivot_high_price": 49.76, "range_contraction_ratio": 0.5,
            "vol_contraction_ratio": 0.4, "base_age": 10, "fresh_tight_fires": False, "reason": "x",
            "breakout_close": 52.0, "base_high": 50.0, "breakout_volume_ratio": 2.0}


@pytest.mark.asyncio
async def test_a_deal_pinned_triggered_name_is_demoted_with_no_licence_on_the_persisted_row(monkeypatch):
    from datetime import date
    from agents.market_intelligence import briefing, ma_filter
    w = _World()

    async def _insert(r):
        w.inserted.append(dict(r))

    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[])
    monkeypatch.setattr(briefing, "send_telegram_message", AsyncMock(return_value=True))
    monkeypatch.setattr(db, "log_audit_event", AsyncMock())
    monkeypatch.setattr(db, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(db, "insert_flag_candidate", _insert)
    monkeypatch.setattr(db, "get_yesterday_flag_state", AsyncMock(return_value=({}, set())))
    monkeypatch.setattr(db, "get_recent_flag_stages", AsyncMock(return_value={}))
    monkeypatch.setattr(db, "get_rs_for_tickers", AsyncMock(return_value={}))
    monkeypatch.setattr(db, "get_sectors_batch", AsyncMock(return_value={}))
    monkeypatch.setattr(db, "get_yesterday_flag_pivots", AsyncMock(return_value={}))
    monkeypatch.setattr(db, "get_flag_failure_carry", AsyncMock(return_value={}))
    monkeypatch.setattr(db, "get_flag_universe", AsyncMock(return_value={"DEAL": ["rs_top200"], "FREE": ["rs_top200"]}))
    monkeypatch.setattr(db, "get_recent_daily_history", AsyncMock(return_value=[{}] * 80))
    monkeypatch.setattr(fd, "compute_flag_metrics", lambda history, ticker=None, **kw: _triggered_row(ticker))
    monkeypatch.setattr(fd, "reconcile_flag_state_post_eod", AsyncMock())
    monkeypatch.setattr(ma_filter, "is_likely_ma", AsyncMock(return_value=(False, {})))
    monkeypatch.setattr(ma_filter, "should_log_mna_filter_fired", AsyncMock(return_value=True))
    sig = {"is_pin": True, "is_fresh_pin": False, "median_range_pct": 0.002, "sub_threshold_days": 8, "total_days": 9}
    monkeypatch.setattr(fd, "_check_deal_pin_signatures_batch", AsyncMock(return_value={"DEAL": sig}))

    by_stage = await fd.run_flag_scan(date(2026, 10, 12))
    last = {r["ticker"]: r for r in w.inserted}                  # the later upsert wins on (ticker, scan_date)
    assert last["DEAL"]["stage"] == "unqualified" and last["DEAL"]["triggered_from"] is None
    assert last["FREE"]["stage"] == "TRIGGERED" and last["FREE"]["triggered_from"] == "tightening"
    assert [r["ticker"] for r in by_stage["TRIGGERED"]] == ["FREE"]


# -- 6b. the breakout tracking tables and the stamp agree -------------------------------------------------------------
# mi_flag_breaks / mi_htf_breakout_shadow record `parent_stage` = the stage of the flag's LAST stored row when the
# intraday break fired. `triggered_from` = the strongest licence anywhere in the 5-day window. They are different
# facts that must never contradict: if the last stored label is COILED the breakout can only be 'coiled'; if it is
# TIGHTENING it is 'coiled' or 'tightening', never 'retrigger'; a TRIGGERED parent may be any bucket.

def test_a_parent_stage_never_contradicts_the_bucket_for_every_possible_window():
    import itertools
    labels = ("WATCH", "TIGHTENING", "COILED", "TRIGGERED", "INVALIDATED", "unqualified")
    strong = {"COILED", "TIGHTENING", "TRIGGERED"}
    n = 0
    for length in range(1, 5):
        for window in itertools.product(labels, repeat=length):
            bucket = fd.trigger_licence(False, list(window))
            parent = window[-1]
            n += 1
            if parent == "COILED":
                assert bucket == "coiled", window
            elif parent == "TIGHTENING":
                assert bucket in ("coiled", "tightening"), window
            elif parent == "TRIGGERED":
                assert bucket is not None, window
            assert (bucket is None) == (not (set(window) & strong)), window
    assert n == sum(6 ** k for k in range(1, 5))


@pytest.mark.asyncio
async def test_a_news_nominated_pinned_triggered_name_is_demoted_with_no_licence_too(monkeypatch):
    from datetime import date
    from agents.market_intelligence import briefing, ma_filter
    inserted = []

    async def _insert(r):
        inserted.append(dict(r))

    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[])
    monkeypatch.setattr(briefing, "send_telegram_message", AsyncMock(return_value=True))
    monkeypatch.setattr(db, "log_audit_event", AsyncMock())
    monkeypatch.setattr(db, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(db, "insert_flag_candidate", _insert)
    monkeypatch.setattr(db, "get_yesterday_flag_state", AsyncMock(return_value=({}, set())))
    monkeypatch.setattr(db, "get_recent_flag_stages", AsyncMock(return_value={}))
    monkeypatch.setattr(db, "get_rs_for_tickers", AsyncMock(return_value={}))
    monkeypatch.setattr(db, "get_sectors_batch", AsyncMock(return_value={}))
    monkeypatch.setattr(db, "get_yesterday_flag_pivots", AsyncMock(return_value={}))
    monkeypatch.setattr(db, "get_flag_failure_carry", AsyncMock(return_value={}))
    monkeypatch.setattr(db, "get_flag_universe", AsyncMock(return_value={"DEAL": ["rs_top200"]}))
    monkeypatch.setattr(db, "get_recent_daily_history", AsyncMock(return_value=[{}] * 80))
    monkeypatch.setattr(fd, "compute_flag_metrics", lambda history, ticker=None, **kw: _triggered_row(ticker))
    monkeypatch.setattr(fd, "reconcile_flag_state_post_eod", AsyncMock())
    monkeypatch.setattr(fd, "_check_deal_pin_signatures_batch", AsyncMock(return_value={}))
    monkeypatch.setattr(ma_filter, "should_log_mna_filter_fired", AsyncMock(return_value=True))
    monkeypatch.setattr(ma_filter, "is_likely_ma",
                        AsyncMock(return_value=(True, {"source": "polygon_headline_model"})))

    await fd.run_flag_scan(date(2026, 10, 12))
    last = inserted[-1]
    assert last["ticker"] == "DEAL" and last["stage"] == "unqualified" and last["triggered_from"] is None
    assert last["original_stage"] == "TRIGGERED"


# -- 7. display: the bucket shows wherever the stage shows ---------------------------------------------------------------

@pytest.mark.parametrize("bucket,text", [("coiled", "from COILED"), ("tightening", "from TIGHTENING"),
                                         ("retrigger", "re-trigger"), (None, ""), ("", ""), ("bogus", "")])
def test_the_label_per_bucket(bucket, text):
    assert fd.triggered_from_label({"triggered_from": bucket}) == text
    assert fd.triggered_from_label({}) == ""


def test_the_bucket_summary_counts_each_path_and_stays_silent_on_legacy_rows():
    rows = [{"triggered_from": "coiled"}, {"triggered_from": "tightening"}, {"triggered_from": "tightening"},
            {"triggered_from": "retrigger"}, {"triggered_from": None}]
    assert fd.triggered_bucket_summary(rows) == "1 from COILED · 2 from TIGHTENING · 1 re-trigger"
    assert fd.triggered_bucket_summary([{"triggered_from": None}]) == ""
    assert fd.triggered_bucket_summary([]) == ""


def _board(*rows):
    out = {s: [] for s in ("TRIGGERED", "COILED", "TIGHTENING", "WATCH", "INVALIDATED", "unqualified")}
    for r in rows:
        out[r["stage"]].append(r)
    return out


def _trig(ticker, bucket):
    r = _triggered_row(ticker)
    r["triggered_from"] = bucket
    return r


def test_the_digest_row_and_header_name_the_path():
    from datetime import date
    text = fd.build_flag_digest(_board(_trig("AAA", "tightening"), _trig("BBB", "coiled")), date(2026, 10, 12), [])
    assert "<code>AAA</code> — from TIGHTENING" in text
    assert "<code>BBB</code> — from COILED" in text
    assert "1 from COILED · 1 from TIGHTENING" in text
    assert "|" not in text.replace("<code>", "").replace("</code>", "")      # Telegram renders no pipe tables


def test_a_legacy_triggered_row_with_no_stamp_renders_exactly_as_before():
    from datetime import date
    legacy = _trig("OLD", None)
    text = fd.build_flag_digest(_board(legacy), date(2026, 10, 12), [])
    assert "<code>OLD</code> — base 10d" in text and "from " not in text and "re-trigger" not in text


def _agent_board(monkeypatch, rows):
    from agents.market_intelligence.agent import MarketIntelligenceAgent
    from agents.market_intelligence.collector import et_today
    from shared.models import AgentRequest

    class _Conn:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def fetchval(self, *a, **kw): return et_today()

    class _Pool:
        def acquire(self): return _Conn()

    monkeypatch.setattr(db, "get_pool", AsyncMock(return_value=_Pool()))
    monkeypatch.setattr(db, "get_flag_candidates_window", AsyncMock(return_value=rows))
    monkeypatch.setattr(db, "get_htf_breakout_shadow_summary", AsyncMock(return_value={}))
    return MarketIntelligenceAgent(), AgentRequest


@pytest.mark.asyncio
async def test_the_flags_board_names_the_path_on_each_triggered_row(monkeypatch):
    rows = [dict(_trig("AAA", "tightening"), runup_pct=1.3), dict(_trig("BBB", "retrigger"), runup_pct=1.1),
            dict(_trig("CCC", None), runup_pct=1.0)]
    agent, Req = _agent_board(monkeypatch, rows)
    res = await agent._handle_flag_query(Req(task="/flags", user_id=1, conversation_id="t"))
    text = res.result
    assert "`AAA` — from TIGHTENING" in text and "`BBB` — re-trigger" in text
    assert "`CCC` — base 10d" in text                              # legacy / NULL: unchanged
    assert "1 from TIGHTENING · 1 re-trigger" in text
    assert "|" not in text


@pytest.mark.asyncio
async def test_the_ticker_history_names_the_path_and_never_on_a_hold(monkeypatch):
    from agents.market_intelligence.agent import MarketIntelligenceAgent
    from shared.models import AgentRequest
    hist = [
        {"scan_date": "2026-10-09", "stage": "TRIGGERED", "base_age": 8, "range_contraction_ratio": 0.5,
         "vol_contraction_ratio": 0.4, "held_from_stage": "WATCH", "triggered_from": None,
         "fresh_tight_fires": False, "fresh_2bar_tr_pct": None, "atr14_pct": None},
        {"scan_date": "2026-10-08", "stage": "TRIGGERED", "base_age": 7, "range_contraction_ratio": 0.5,
         "vol_contraction_ratio": 0.4, "held_from_stage": None, "triggered_from": "tightening",
         "fresh_tight_fires": False, "fresh_2bar_tr_pct": None, "atr14_pct": None},
    ]
    monkeypatch.setattr(db, "get_ticker_flag_history", AsyncMock(return_value=hist))
    res = await MarketIntelligenceAgent()._handle_flag_query(AgentRequest(task="/flags TST", user_id=1, conversation_id="t"))
    lines = {ln.split()[0]: ln for ln in res.result.splitlines() if ln.strip().startswith("2026-")}
    assert "from TIGHTENING" in lines["2026-10-08"]
    assert "(held from WATCH)" in lines["2026-10-09"] and "from TIGHTENING" not in lines["2026-10-09"]
