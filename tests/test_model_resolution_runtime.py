"""#509 model auto-resolution — agents/market_intelligence/model_resolution.py's
runtime pieces: current_role_bindings/_role_source, the boot recorder, the
nightly refresh, and the NEW nightly eval-divergence guardrail.

Pins:
  1. current_role_bindings reports the RESOLVED value for a RESOLVED_ROLES role
     (not the plain static constant) — the boot recorder's whole point is to
     record the TRUE running value.
  2. _role_source is role-driven: a role outside RESOLVED_ROLES is always
     "static", regardless of what family its literal id happens to parse into.
  3. record_boot_resolution: baseline (first-ever) writes are audit-only, never
     Telegram'd; a REAL change writes + audits + Telegrams; a no-op boot writes
     nothing; the whole function never raises.
  4. refresh_model_resolution: first run records candidates without spamming
     Telegram (no prior binding to compare against); a genuine new release on a
     tier Telegrams + audits, and calls out any RESOLVED_ROLES role riding that
     tier; a disappeared-tier is accepted loudly; an empty models.list raises
     (so audit_wrap marks the run failed) without touching the cache.
  5. check_judge_eval_divergence: match -> silent; mismatch -> WARN (audit +
     Telegram), never a block; missing/corrupt record -> a loud error event,
     never a raise; a downstream exception is swallowed, never propagates.
"""
import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from agents.market_intelligence import model_resolution as mr
from shared import llm_models
from shared.model_resolver import TierResolution


def _run(coro):
    return asyncio.run(coro)


# ─── current_role_bindings / _role_source ───────────────────────────────────

def test_current_role_bindings_reports_resolved_value_for_judge(monkeypatch):
    fake = TierResolution("opus", "claude-opus-5", "cache", "2026-07-30T00:00:00+00:00", "")
    monkeypatch.setitem(llm_models._ROLE_RESOLUTIONS, "JUDGE_MODEL", fake)
    bindings = mr.current_role_bindings()
    assert bindings["JUDGE_MODEL"] == "claude-opus-5"
    assert bindings["THEME_MODEL"] == llm_models.THEME_MODEL


def test_role_source_static_for_non_resolved_role():
    """Only JUDGE_DIVERGENCE_MODEL is un-tracked now (operator opted all other
    roles in 2026-07-31); it stays static ON PURPOSE so it remains an
    INDEPENDENT second read on the judge."""
    from shared import llm_models
    assert llm_models.role_resolution("JUDGE_DIVERGENCE_MODEL") is None
    assert llm_models.effective_model("JUDGE_DIVERGENCE_MODEL") == \
        llm_models.JUDGE_DIVERGENCE_MODEL



def test_role_source_reads_the_real_resolution(monkeypatch):
    fake = TierResolution("opus", "claude-opus-5", "cache", "2026-07-30T00:00:00+00:00", "some note")
    monkeypatch.setitem(llm_models._ROLE_RESOLUTIONS, "JUDGE_MODEL", fake)
    source, note = mr._role_source("JUDGE_MODEL", "claude-opus-5")
    assert source == "cache"
    assert note == "some note"


# ─── record_boot_resolution ──────────────────────────────────────────────────

def _mock_boot_deps(monkeypatch, bindings, prior: dict, audit=None, telegram=None):
    monkeypatch.setattr(mr, "runs_intelligence_jobs", lambda: True)
    monkeypatch.setattr(mr, "current_role_bindings", lambda: bindings)

    async def fake_latest(role):
        return {"model": prior[role]} if prior.get(role) is not None else None
    monkeypatch.setattr(mr, "get_latest_model_resolution", fake_latest)

    insert_mock = AsyncMock()
    monkeypatch.setattr(mr, "insert_model_resolution", insert_mock)
    audit_mock = audit if audit is not None else AsyncMock()
    monkeypatch.setattr(mr, "log_audit_event", audit_mock)
    tg_mock = telegram if telegram is not None else AsyncMock()
    monkeypatch.setattr(mr, "_send_telegram", tg_mock)
    return insert_mock, audit_mock, tg_mock


def test_boot_recorder_skips_when_not_intelligence_role(monkeypatch):
    monkeypatch.setattr(mr, "runs_intelligence_jobs", lambda: False)
    called = AsyncMock()
    monkeypatch.setattr(mr, "current_role_bindings", called)
    _run(mr.record_boot_resolution())
    called.assert_not_called()


def test_boot_recorder_baseline_is_audit_only_no_telegram(monkeypatch):
    bindings = {"JUDGE_MODEL": "claude-opus-4-8"}
    insert_mock, audit_mock, tg_mock = _mock_boot_deps(monkeypatch, bindings, prior={})
    _run(mr.record_boot_resolution())
    insert_mock.assert_awaited_once()
    assert insert_mock.await_args.args[3] is None  # prev_model
    fired = [c.args[0] for c in audit_mock.await_args_list]
    assert fired == ["model_resolution_baseline"]
    tg_mock.assert_not_awaited()


def test_boot_recorder_noop_when_unchanged(monkeypatch):
    bindings = {"JUDGE_MODEL": "claude-opus-4-8"}
    insert_mock, audit_mock, tg_mock = _mock_boot_deps(
        monkeypatch, bindings, prior={"JUDGE_MODEL": "claude-opus-4-8"})
    _run(mr.record_boot_resolution())
    insert_mock.assert_not_awaited()
    audit_mock.assert_not_awaited()
    tg_mock.assert_not_awaited()


def test_boot_recorder_real_change_writes_audits_and_telegrams(monkeypatch):
    bindings = {"JUDGE_MODEL": "claude-opus-5", "THEME_MODEL": llm_models.THEME_MODEL}
    insert_mock, audit_mock, tg_mock = _mock_boot_deps(
        monkeypatch, bindings, prior={"JUDGE_MODEL": "claude-opus-4-8", "THEME_MODEL": llm_models.THEME_MODEL})
    _run(mr.record_boot_resolution())
    insert_mock.assert_awaited_once()
    args = insert_mock.await_args.args
    assert args[0] == "JUDGE_MODEL" and args[1] == "claude-opus-5" and args[3] == "claude-opus-4-8"
    fired = [c.args[0] for c in audit_mock.await_args_list]
    assert fired == ["model_resolution_change"]
    tg_mock.assert_awaited_once()
    text = tg_mock.await_args.args[0]
    assert "JUDGE_MODEL" in text and "claude-opus-5" in text
    assert "_TIER_OVERRIDES" in text  # rollback lever always mentioned


def test_boot_recorder_never_raises_on_db_failure(monkeypatch):
    monkeypatch.setattr(mr, "runs_intelligence_jobs", lambda: True)
    monkeypatch.setattr(mr, "current_role_bindings", lambda: {"JUDGE_MODEL": "x"})

    async def boom(role):
        raise RuntimeError("db down")
    monkeypatch.setattr(mr, "get_latest_model_resolution", boom)
    _run(mr.record_boot_resolution())  # must not raise


# ─── refresh_model_resolution ────────────────────────────────────────────────

LIVE_IDS = [
    "claude-opus-5", "claude-sonnet-5", "claude-fable-5",
    "claude-opus-4-8", "claude-opus-4-7", "claude-sonnet-4-6",
    "claude-opus-4-6", "claude-opus-4-5-20251101", "claude-haiku-4-5-20251001",
]


def _mock_refresh_deps(monkeypatch, tmp_path, ids, audit=None, telegram=None):
    monkeypatch.setenv("APOLLO_MODEL_RESOLUTION_CACHE", str(tmp_path / "cache.json"))

    async def fake_list_ids():
        return list(ids)
    monkeypatch.setattr(mr, "_list_model_ids", fake_list_ids)
    audit_mock = audit if audit is not None else AsyncMock()
    monkeypatch.setattr(mr, "log_audit_event", audit_mock)
    tg_mock = telegram if telegram is not None else AsyncMock()
    monkeypatch.setattr(mr, "_send_telegram", tg_mock)
    return audit_mock, tg_mock


def test_refresh_first_run_writes_cache_no_telegram(monkeypatch, tmp_path):
    audit_mock, tg_mock = _mock_refresh_deps(monkeypatch, tmp_path, LIVE_IDS)
    n = _run(mr.refresh_model_resolution())
    assert n == 3
    from shared.model_resolver import read_cache
    cache = read_cache(tmp_path / "cache.json")
    assert cache["resolved"] == {
        "opus": "claude-opus-5", "sonnet": "claude-sonnet-5", "haiku": "claude-haiku-4-5-20251001",
    }
    # first-ever record: audit fires (candidate discovered) but nothing to
    # compare against yet, so no Telegram noise on cold start.
    fired = [c.args[0] for c in audit_mock.await_args_list]
    assert fired.count("model_release_detected") == 3
    tg_mock.assert_not_awaited()


def test_refresh_new_release_telegrams_and_flags_judge(monkeypatch, tmp_path):
    from shared.model_resolver import write_cache
    write_cache({"opus": "claude-opus-4-8", "sonnet": "claude-sonnet-4-6",
                 "haiku": "claude-haiku-4-5-20251001"}, {}, cache_path=tmp_path / "cache.json")
    audit_mock, tg_mock = _mock_refresh_deps(monkeypatch, tmp_path, LIVE_IDS)
    _run(mr.refresh_model_resolution())
    tg_mock.assert_awaited_once()
    text = tg_mock.await_args.args[0]
    assert "opus" in text and "claude-opus-5" in text
    assert "JUDGE_MODEL" in text  # RESOLVED_ROLES-driven callout
    assert "ADR-0030" in text


def test_refresh_disappeared_tier_accepted_loudly(monkeypatch, tmp_path):
    from shared.model_resolver import write_cache
    write_cache({"opus": "claude-opus-99-fictional"}, {}, cache_path=tmp_path / "cache.json")
    audit_mock, tg_mock = _mock_refresh_deps(monkeypatch, tmp_path, LIVE_IDS)
    _run(mr.refresh_model_resolution())
    fired = [c.args[0] for c in audit_mock.await_args_list]
    assert "model_resolution_refresh_anomaly" in fired


def test_refresh_empty_listing_raises_and_leaves_cache_untouched(monkeypatch, tmp_path):
    cache_path = tmp_path / "cache.json"
    from shared.model_resolver import write_cache, read_cache
    write_cache({"opus": "claude-opus-4-8"}, {}, cache_path=cache_path)
    before = read_cache(cache_path)
    _mock_refresh_deps(monkeypatch, tmp_path, [])
    with pytest.raises(RuntimeError):
        _run(mr.refresh_model_resolution())
    assert read_cache(cache_path) == before


# ─── check_judge_eval_divergence ─────────────────────────────────────────────

def _mock_divergence_deps(monkeypatch, tmp_path, record: "dict | None",
                          running: str = "claude-opus-4-8", audit=None, telegram=None):
    monkeypatch.setattr(llm_models, "effective_model", lambda role: running)
    record_path = tmp_path / "judge_eval_pass_record.json"
    if record is not None:
        record_path.write_text(json.dumps(record), encoding="utf-8")
    monkeypatch.setattr(mr, "_EVAL_RECORD_PATH", record_path)
    audit_mock = audit if audit is not None else AsyncMock()
    monkeypatch.setattr(mr, "log_audit_event", audit_mock)
    tg_mock = telegram if telegram is not None else AsyncMock()
    monkeypatch.setattr(mr, "_send_telegram", tg_mock)
    return audit_mock, tg_mock


def test_divergence_silent_when_running_matches_evaluated(monkeypatch, tmp_path):
    audit_mock, tg_mock = _mock_divergence_deps(
        monkeypatch, tmp_path, {"judge_model": "claude-opus-4-8"}, running="claude-opus-4-8")
    _run(mr.check_judge_eval_divergence())
    audit_mock.assert_not_awaited()
    tg_mock.assert_not_awaited()


def test_divergence_warns_never_blocks_on_mismatch(monkeypatch, tmp_path):
    audit_mock, tg_mock = _mock_divergence_deps(
        monkeypatch, tmp_path, {"judge_model": "claude-opus-4-8"}, running="claude-opus-5")
    _run(mr.check_judge_eval_divergence())  # must not raise — WARN only
    audit_mock.assert_awaited_once()
    assert audit_mock.await_args.args[0] == "judge_model_eval_divergence"
    tg_mock.assert_awaited_once()
    text = tg_mock.await_args.args[0]
    assert "claude-opus-5" in text and "claude-opus-4-8" in text


def test_divergence_missing_record_is_loud_not_silent(monkeypatch, tmp_path):
    audit_mock, tg_mock = _mock_divergence_deps(monkeypatch, tmp_path, None)
    _run(mr.check_judge_eval_divergence())
    audit_mock.assert_awaited_once()
    assert audit_mock.await_args.args[0] == "model_resolution_eval_check_error"
    tg_mock.assert_not_awaited()


def test_divergence_corrupt_record_is_loud_not_silent(monkeypatch, tmp_path):
    record_path = tmp_path / "judge_eval_pass_record.json"
    record_path.write_text("{not valid json", encoding="utf-8")
    monkeypatch.setattr(llm_models, "effective_model", lambda role: "claude-opus-4-8")
    monkeypatch.setattr(mr, "_EVAL_RECORD_PATH", record_path)
    audit_mock = AsyncMock()
    monkeypatch.setattr(mr, "log_audit_event", audit_mock)
    monkeypatch.setattr(mr, "_send_telegram", AsyncMock())
    _run(mr.check_judge_eval_divergence())
    audit_mock.assert_awaited_once()
    assert audit_mock.await_args.args[0] == "model_resolution_eval_check_error"


def test_divergence_never_raises_even_if_audit_write_fails(monkeypatch, tmp_path):
    audit_mock = AsyncMock(side_effect=RuntimeError("db down"))
    tg_mock = AsyncMock()
    _mock_divergence_deps(
        monkeypatch, tmp_path, {"judge_model": "claude-opus-4-8"}, running="claude-opus-5",
        audit=audit_mock, telegram=tg_mock,
    )
    _run(mr.check_judge_eval_divergence())  # must not raise
