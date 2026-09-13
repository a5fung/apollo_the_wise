"""#651 — the judge names groups on EP alerts that our theme engine does not have; capture them,
then MEASURE HOW LATE THE ENGINE IS (recurrence across >=2 tickers before a matching theme).

Groups:
  1. Pure read logic: key normalisation, recurrence (>=2 distinct tickers, no threshold), theme
     matching (deterministic, rename-lineage aware, never on one generic shared token), lead time.
  2. The extraction call (fake client): structured tool output in, rows out; fail-open on error /
     truncation; no call at all on an empty rationale (no spend).
  3. The nightly sweep: writes one row per named group + a sentinel row when nothing is named (so
     the same alert is never re-billed), skips the write on failure (retry next night), captures
     raw output to JSONL BEFORE touching the DB.
  4. Wiring gates: shadow-writer registration (identity), CREATE carries the idempotency key,
     job classified INTELLIGENCE + scheduled off the alert hot path, registry role/label/ceiling.
  5. THE LINE + anti-circularity: the new table is read by NOTHING that grades, promotes, or
     feeds the judge's own inputs — it is a recorder for the operator's ruling only.
"""
from __future__ import annotations

import asyncio
import datetime as _dt
import json
import re
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from tests.conftest import make_mock_pool

from agents.market_intelligence import db as dbmod
from agents.market_intelligence import judge_named_themes as jnt

_REPO = Path(__file__).resolve().parent.parent
_D = _dt.date


def _run(coro):
    return asyncio.run(coro)


def _row(ticker, day, key, name=None, evidence="", untracked=None):
    return {
        "ticker": ticker, "alert_date": _D(2026, 8, day), "canonical_key": key,
        "group_name": name or key, "evidence": evidence, "judge_says_untracked": untracked,
    }


# ════════════════════════════════════════════════════════════════════════════════════
# 1. Pure read logic

def test_normalize_key_collapses_phrasings_of_the_same_group():
    assert jnt.normalize_key("the live AI infrastructure theme") == "ai-infrastructure"
    assert jnt.normalize_key("AI-Infrastructure") == "ai-infrastructure"
    assert jnt.normalize_key("LNG export cohorts") == "lng-export"
    assert jnt.normalize_key("AI data-center power buildout") == "ai-data-center-power-buildout"


def test_normalize_key_is_empty_for_noise_only_input():
    assert jnt.normalize_key("the theme") == ""
    assert jnt.normalize_key("") == ""
    assert jnt.normalize_key(None) == ""


def test_recurring_groups_requires_two_distinct_tickers_not_two_mentions():
    rows = [
        _row("AAA", 1, "ai-infrastructure"), _row("AAA", 3, "ai-infrastructure"),  # same ticker twice
        _row("BBB", 2, "lng-export"), _row("CCC", 5, "LNG export"),               # two tickers
        _row("DDD", 6, jnt.NONE_KEY),                                              # sentinel
    ]
    groups = jnt.recurring_groups(rows)
    assert [g["key"] for g in groups] == ["lng-export"]
    g = groups[0]
    assert g["n_tickers"] == 2 and g["n_alerts"] == 2
    assert g["first_named_date"] == _D(2026, 8, 2)
    assert g["tickers"] == ["BBB", "CCC"]
    assert sorted(g["variants"]) == ["LNG export", "lng-export"]


def test_recurring_groups_ignores_the_sentinel_even_across_tickers():
    rows = [_row("AAA", 1, jnt.NONE_KEY), _row("BBB", 2, jnt.NONE_KEY)]
    assert jnt.recurring_groups(rows) == []


def _history(*items):
    """(name, first_date) -> the theme-history rows shape the read consumes."""
    return [{"name": n, "theme_date": d} for n, d in items]


def test_lead_time_is_positive_when_the_judge_named_it_before_the_engine():
    rows = [_row("AAA", 1, "ai-data-center-power"), _row("BBB", 4, "AI data center power")]
    hist = _history(("AI Data Center Power", _D(2026, 8, 15)), ("AI Data Center Power", _D(2026, 8, 16)))
    rep = jnt.lead_time_report(rows, hist)
    assert rep["n_recurring"] == 1
    g = rep["groups"][0]
    assert g["match"]["theme_name"] == "AI Data Center Power"
    assert g["match"]["theme_first_date"] == _D(2026, 8, 15)
    assert g["lead_days"] == 14
    assert g["verdict"] == "judge_earlier"


def test_lead_time_is_already_existed_when_the_engine_was_first():
    rows = [_row("AAA", 10, "ai-data-center-power"), _row("BBB", 12, "ai-data-center-power")]
    hist = _history(("AI Data Center Power", _D(2026, 7, 1)))
    g = jnt.lead_time_report(rows, hist)["groups"][0]
    assert g["verdict"] == "already_existed"
    assert g["lead_days"] == -40


def test_lead_time_never_matched_when_no_theme_ever_resembled_it():
    rows = [_row("AAA", 1, "lng-export"), _row("BBB", 2, "lng-export")]
    hist = _history(("AI Data Center Power", _D(2026, 7, 1)))
    g = jnt.lead_time_report(rows, hist)["groups"][0]
    assert g["verdict"] == "never_matched"
    assert g["match"] is None and g["lead_days"] is None


def test_theme_match_follows_rename_lineage_to_the_earliest_name():
    rows = [_row("AAA", 20, "grid-power"), _row("BBB", 22, "grid-power")]
    hist = _history(("Grid Power", _D(2026, 9, 1)), ("Utility Grid Power", _D(2026, 7, 15)))
    edges = [("Utility Grid Power", "Grid Power")]
    g = jnt.lead_time_report(rows, hist, rename_edges=edges)["groups"][0]
    assert g["match"]["theme_first_date"] == _D(2026, 7, 15)
    assert g["verdict"] == "already_existed"


def test_theme_match_never_fires_on_a_single_generic_shared_token():
    # "ai-chip" vs "AI Data Center Power": one shared token ('ai') is not a match — but it IS
    # listed as a near-miss so the operator can eyeball it.
    rows = [_row("AAA", 1, "ai-chip"), _row("BBB", 2, "ai-chip")]
    hist = _history(("AI Data Center Power", _D(2026, 7, 1)))
    g = jnt.lead_time_report(rows, hist)["groups"][0]
    assert g["match"] is None
    assert [m["theme_name"] for m in g["near_misses"]] == ["AI Data Center Power"]


def test_theme_match_accepts_containment_of_two_or_more_tokens():
    rows = [_row("AAA", 1, "ai-infrastructure"), _row("BBB", 2, "ai-infrastructure")]
    hist = _history(("AI Infrastructure Buildout", _D(2026, 8, 20)))
    g = jnt.lead_time_report(rows, hist)["groups"][0]
    assert g["match"]["theme_name"] == "AI Infrastructure Buildout"
    assert g["lead_days"] == 19


def test_report_counts_carry_n_for_every_number():
    rows = [
        _row("AAA", 1, "ai-infrastructure"), _row("BBB", 2, "ai-infrastructure"),
        _row("CCC", 3, "lng-export"), _row("DDD", 4, jnt.NONE_KEY),
    ]
    rep = jnt.lead_time_report(rows, _history(("AI Infrastructure", _D(2026, 8, 30))))
    assert rep["n_alerts_extracted"] == 4
    assert rep["n_alerts_naming_a_group"] == 3
    assert rep["n_distinct_keys"] == 2
    assert rep["n_recurring"] == 1
    assert rep["n_singletons"] == 1
    assert rep["n_judge_earlier"] == 1 and rep["n_already_existed"] == 0 and rep["n_never_matched"] == 0


def test_format_report_leads_with_the_answer():
    rows = [_row("AAA", 1, "ai-infrastructure"), _row("BBB", 2, "ai-infrastructure")]
    text = jnt.format_report(jnt.lead_time_report(rows, _history(("AI Infrastructure", _D(2026, 8, 30)))))
    first = text.splitlines()[0]
    assert first.startswith("MEASURED") and "1 group" in first and "29d" in first
    null_text = jnt.format_report(jnt.lead_time_report([_row("AAA", 1, "x")], []))
    assert null_text.splitlines()[0].startswith("NULL")


# ════════════════════════════════════════════════════════════════════════════════════
# 2. The extraction call

class _Block:
    type = "tool_use"

    def __init__(self, inp):
        self.input = inp


class _Resp:
    def __init__(self, inp, stop="tool_use", usage=(300, 60)):
        self.content = [_Block(inp)]
        self.stop_reason = stop
        self.usage = type("U", (), {"input_tokens": usage[0], "output_tokens": usage[1]})()


class _FakeClient:
    def __init__(self, inp=None, raise_exc=None, stop="tool_use"):
        self.calls = []

        async def _create(**kw):
            self.calls.append(kw)
            if raise_exc:
                raise raise_exc
            return _Resp(inp, stop=stop)

        self.messages = type("M", (), {"create": staticmethod(_create)})()


@pytest.fixture
def no_spend_log(monkeypatch):
    async def _noop(**_kw):
        return None
    monkeypatch.setattr("agents.market_intelligence.spend_tracker.log_anthropic_call_safe", _noop)


_RATIONALE = ("AGX gaps on a strong print. The stock trades with the ag re-rating and the LNG "
              "export cohorts; no active theme matched.")


def test_extract_returns_structured_groups_from_the_tool_output(monkeypatch, no_spend_log):
    client = _FakeClient({"groups": [
        {"name": "ag re-rating", "canonical_key": "ag-re-rating",
         "evidence": "The stock trades with the ag re-rating", "judge_says_untracked": True},
        {"name": "LNG export cohorts", "canonical_key": "lng-export",
         "evidence": "x" * 400, "judge_says_untracked": True},
    ]})
    monkeypatch.setattr(jnt, "_get_client", lambda: client)
    out = _run(jnt.extract_named_themes("AGX", _D(2026, 9, 3), _RATIONALE))
    assert out is not None
    assert [g["canonical_key"] for g in out["groups"]] == ["ag-re-rating", "lng-export"]
    assert len(out["groups"][1]["evidence"]) == jnt.MAX_EVIDENCE_LEN
    assert out["input_tokens"] == 300 and out["output_tokens"] == 60
    kw = client.calls[0]
    assert kw["tool_choice"] == {"type": "tool", "name": jnt.EXTRACT_TOOL["name"]}
    assert _RATIONALE in kw["messages"][0]["content"]


def test_extract_drops_groups_with_no_usable_key(monkeypatch, no_spend_log):
    client = _FakeClient({"groups": [
        {"name": "the theme", "canonical_key": "", "evidence": "", "judge_says_untracked": False},
        {"name": "bitcoin miners", "canonical_key": "bitcoin-miner", "evidence": "e"},
    ]})
    monkeypatch.setattr(jnt, "_get_client", lambda: client)
    out = _run(jnt.extract_named_themes("X", _D(2026, 9, 3), _RATIONALE))
    assert [g["canonical_key"] for g in out["groups"]] == ["bitcoin-miner"]


def test_extract_is_none_on_a_client_error_and_never_raises(monkeypatch, no_spend_log):
    monkeypatch.setattr(jnt, "_get_client", lambda: _FakeClient(raise_exc=RuntimeError("boom")))
    assert _run(jnt.extract_named_themes("X", _D(2026, 9, 3), _RATIONALE)) is None


def test_extract_is_none_on_truncation(monkeypatch, no_spend_log):
    monkeypatch.setattr(jnt, "_get_client", lambda: _FakeClient({"groups": []}, stop="max_tokens"))
    assert _run(jnt.extract_named_themes("X", _D(2026, 9, 3), _RATIONALE)) is None


def test_extract_makes_no_call_on_an_empty_rationale(monkeypatch, no_spend_log):
    client = _FakeClient({"groups": []})
    monkeypatch.setattr(jnt, "_get_client", lambda: client)
    out = _run(jnt.extract_named_themes("X", _D(2026, 9, 3), "   "))
    assert out == {"groups": [], "input_tokens": 0, "output_tokens": 0, "model": None}
    assert client.calls == []


# ════════════════════════════════════════════════════════════════════════════════════
# 3. The nightly sweep

def _pending(*items):
    return [{"id": i, "ticker": t, "alert_date": _D(2026, 9, d), "judge_rationale": r}
            for i, (t, d, r) in enumerate(items, start=1)]


def test_sweep_writes_named_rows_plus_a_sentinel_and_captures_first(monkeypatch, tmp_path):
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=_pending(("AGX", 3, _RATIONALE), ("SNOW", 3, "no group here")))
    conn.execute = AsyncMock()
    monkeypatch.setattr(jnt, "get_pool", AsyncMock(return_value=pool))

    async def _fake_extract(ticker, alert_date, rationale):
        if ticker == "AGX":
            return {"groups": [
                {"name": "ag re-rating", "canonical_key": "ag-re-rating", "evidence": "e1", "judge_says_untracked": True},
                {"name": "LNG export", "canonical_key": "lng-export", "evidence": "e2", "judge_says_untracked": True},
            ], "input_tokens": 300, "output_tokens": 60, "model": "m"}
        return {"groups": [], "input_tokens": 200, "output_tokens": 20, "model": "m"}
    monkeypatch.setattr(jnt, "extract_named_themes", _fake_extract)
    cap = tmp_path / "cap.jsonl"

    out = _run(jnt.extract_pending(limit=10, capture_path=cap))

    assert out["n_alerts"] == 2 and out["n_rows_written"] == 3 and out["n_failed"] == 0
    keys = [c.args[5] for c in conn.execute.call_args_list if c.args and c.args[0] is dbmod.JUDGE_NAMED_THEME_INSERT_SQL]
    assert keys == ["ag-re-rating", "lng-export", jnt.NONE_KEY]
    lines = [json.loads(l) for l in cap.read_text().splitlines()]
    assert [l["ticker"] for l in lines] == ["AGX", "SNOW"]
    assert lines[0]["groups"][0]["canonical_key"] == "ag-re-rating"
    assert out["input_tokens"] == 500 and out["output_tokens"] == 80
    assert out["est_cost_usd"] == pytest.approx(500 * 1.0 / 1e6 + 80 * 5.0 / 1e6)


def test_sweep_skips_the_write_on_a_failed_extraction_so_it_retries_next_night(monkeypatch, tmp_path):
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=_pending(("AGX", 3, _RATIONALE)))
    conn.execute = AsyncMock()
    monkeypatch.setattr(jnt, "get_pool", AsyncMock(return_value=pool))

    async def _fail(*_a, **_k):
        return None
    monkeypatch.setattr(jnt, "extract_named_themes", _fail)

    out = _run(jnt.extract_pending(limit=10, capture_path=tmp_path / "c.jsonl"))
    assert out["n_failed"] == 1 and out["n_rows_written"] == 0
    assert not any(c.args and c.args[0] is dbmod.JUDGE_NAMED_THEME_INSERT_SQL for c in conn.execute.call_args_list)


def test_sweep_dry_run_spends_nothing_and_writes_nothing(monkeypatch):
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=_pending(("AGX", 3, _RATIONALE)))
    conn.execute = AsyncMock()
    monkeypatch.setattr(jnt, "get_pool", AsyncMock(return_value=pool))
    called = []

    async def _spy(*a, **k):
        called.append(a)
        return {"groups": [], "input_tokens": 1, "output_tokens": 1, "model": "m"}
    monkeypatch.setattr(jnt, "extract_named_themes", _spy)

    out = _run(jnt.extract_pending(limit=10, commit=False))
    assert out["n_alerts"] == 1 and called == [] and conn.execute.call_count == 0


def test_pending_query_excludes_already_extracted_alerts_and_bounds_the_batch():
    sql = dbmod.JUDGE_NAMED_THEMES_PENDING_SQL
    assert "judge_rationale IS NOT NULL" in sql
    assert "NOT EXISTS" in sql and "mi_judge_named_themes" in sql
    assert "LIMIT $2" in sql
    # a duplicate mi_ep_alerts row for one (ticker, alert_date) is billed once, not twice
    assert "DISTINCT ON (a.ticker, a.alert_date)" in sql


def test_writer_keeps_the_ticker_exactly_as_the_alert_holds_it():
    """The pending query joins j.ticker = a.ticker EXACTLY. Uppercasing on write would make a
    non-uppercase alert ticker pending — and billed — every single night."""
    pool, conn = make_mock_pool()
    conn.execute = AsyncMock()
    _run(dbmod.insert_judge_named_theme_row(conn, "brk.b", _D(2026, 9, 3), 7, "x", "x", None, None, "m"))
    assert conn.execute.call_args.args[1] == "brk.b"


# ════════════════════════════════════════════════════════════════════════════════════
# 4. Wiring gates

def test_insert_is_registered_as_a_shadow_writer_by_identity():
    from scripts.preflight_db_updates import SHADOW_WRITER_STATEMENTS
    assert any(sql is dbmod.JUDGE_NAMED_THEME_INSERT_SQL for _, sql in SHADOW_WRITER_STATEMENTS)


def test_create_table_declares_the_idempotency_key_and_no_alter_exists():
    src = (_REPO / "agents" / "market_intelligence" / "db.py").read_text()
    start = src.index("CREATE TABLE IF NOT EXISTS mi_judge_named_themes")
    block = src[start:src.index(");", start)]
    assert "UNIQUE (ticker, alert_date, canonical_key)" in block
    assert "canonical_key TEXT NOT NULL" in block
    assert "evidence TEXT" in block
    assert "ALTER TABLE mi_judge_named_themes" not in src
    assert "ON CONFLICT (ticker, alert_date, canonical_key) DO NOTHING" in dbmod.JUDGE_NAMED_THEME_INSERT_SQL


def test_job_is_intelligence_owned_and_scheduled_off_the_alert_hot_path():
    from agents.market_intelligence import scheduler as sched
    assert "judge_named_themes_extract" in sched.INTELLIGENCE_OWNED_JOB_IDS
    assert "judge_named_themes_extract" not in sched.EXECUTION_OWNED_JOB_IDS
    src = (_REPO / "agents" / "market_intelligence" / "scheduler.py").read_text()
    m = re.search(r'CronTrigger\(hour=(\d+), minute=(\d+), day_of_week="mon-fri"[^)]*\)\s*,\s*\n\s*'
                  r'id="judge_named_themes_extract"', src)
    assert m, "job not registered with a mon-fri CronTrigger"
    hour, minute = int(m.group(1)), int(m.group(2))
    assert (hour, minute) == (18, 20), "runs after the day's alerts, clear of both deploy windows"
    # NOT in the alert path: the scan tick never waits on a Haiku call for this.
    ep = (_REPO / "agents" / "market_intelligence" / "ep_detector.py").read_text()
    assert "judge_named_themes" not in ep


def test_registry_role_label_and_ceiling_are_wired():
    from shared import llm_models, output_ceilings as oc
    assert llm_models.RESOLVED_ROLES["JUDGE_NAMED_THEMES_MODEL"] == "haiku"
    assert "JUDGE_NAMED_THEMES_MODEL" in llm_models.ROLE_LABELS
    assert llm_models.tier_of(llm_models.JUDGE_NAMED_THEMES_MODEL) == "haiku"
    assert oc.CEILINGS["judge_named_themes"].role == "JUDGE_NAMED_THEMES_MODEL"
    assert jnt.JUDGE_NAMED_THEMES_MODEL == llm_models.JUDGE_NAMED_THEMES_MODEL


# ════════════════════════════════════════════════════════════════════════════════════
# 5. THE LINE + anti-circularity

def test_the_table_feeds_nothing_that_grades_promotes_or_informs_the_judge():
    """A judge-named group must never become the judge's own corroborating evidence (#322's
    wall), never auto-create a theme, and never touch a grade/entry/exit/size path."""
    mi = _REPO / "agents" / "market_intelligence"
    for rel in ("ep_grade_judge.py", "theme_engine.py", "ep_detector.py", "entry_pipeline.py"):
        p = mi / rel
        if p.exists():
            assert "mi_judge_named_themes" not in p.read_text(), rel
    # the judge's own narrative feed never selects from it
    import inspect
    assert "mi_judge_named_themes" not in inspect.getsource(dbmod.get_narrative_theme_candidates)
    # the module itself writes ONLY its own table
    src = (mi / "judge_named_themes.py").read_text()
    assert "INSERT INTO mi_themes" not in src and "mi_theme_candidates_shadow" not in src
    assert "UPDATE mi_ep_alerts" not in src
