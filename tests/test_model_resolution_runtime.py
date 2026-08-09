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
    """EVERY registry role is tracked now (operator 2026-07-31: "all models need
    a path to upgrade, nothing shall remain stale"), so the un-tracked branch has
    no real role left to exercise — assert it against a synthetic name instead of
    deleting the coverage. `_role_source` must degrade to "static", never raise,
    for anything it doesn't know.
    """
    assert llm_models.role_resolution("SOME_FUTURE_MODEL") is None
    assert llm_models.effective_model("SOME_FUTURE_MODEL") == ""
    source, note = mr._role_source("SOME_FUTURE_MODEL", "claude-whatever")
    assert source == "static"
    assert "not in RESOLVED_ROLES" in note



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
    # The ceilings sweep (2026-08-09) rides the same change event: JUDGE_MODEL has
    # registered output ceilings, so the drift audit fires right after the change one.
    assert fired == ["model_resolution_change", "output_ceilings_model_drift"]
    tg_mock.assert_awaited_once()
    text = tg_mock.await_args.args[0]
    # Operator-facing wording (operator 2026-07-31 "could use some better
    # formatting"): plain-words role names and versions, NOT our constants and
    # raw ids. Pins the intent, so a revert to the log-dump form fails here.
    assert "grading judge" in text and "Opus 4.8 → Opus 5" in text
    assert "JUDGE_MODEL" not in text and "claude-opus-5" not in text
    # Ceilings sweep section: the callers whose max_tokens was sized on the
    # outgoing model are named at the binding moment, not after the first cut.
    assert "sized on the previous model" in text
    assert "ep_grade_judge" in text and "mgmt_judge" in text
    assert "Undo:" in text  # rollback lever always mentioned


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
    assert "Opus 4.8 → Opus 5" in text and "claude-opus-5" not in text
    # the callout is still RESOLVED_ROLES-driven, but named in plain words
    assert "grading judge" in text and "JUDGE_MODEL" not in text
    # the judge-eval caveat survives the rewording — it just no longer cites an
    # ADR number, a gate filename and a docstring at the operator
    assert "last evaluation did not cover" in text
    assert "ADR-0030" not in text and "preflight_judge_eval_gate" not in text


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


# ─── fallback-pin staleness (operator 2026-07-31: nothing shall remain stale) ─

def _dt(days_ago: int) -> str:
    from datetime import datetime, timedelta, timezone
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


def test_stale_tier_pins_quiet_when_pin_equals_served():
    from shared import llm_models
    resolved = dict(llm_models._TIER_PINS)          # served == pinned everywhere
    changed = {t: _dt(400) for t in resolved}
    assert mr.stale_tier_pins(resolved, changed) == []


def test_stale_tier_pins_quiet_inside_the_grace_window():
    """A release that landed yesterday is NOT drift — the pin is allowed to lag
    while the new model is still being watched."""
    resolved = {"opus": "claude-opus-5"}
    assert mr.stale_tier_pins(resolved, {"opus": _dt(3)}) == []


def test_stale_tier_pins_reports_a_pin_left_behind_for_a_month():
    # SERVED must be a model the pin is NOT. Anchored on a hypothetical future id rather than a
    # real one: this asserts the drift MECHANISM, and pinning it to whatever opus id is current
    # made it silently stop testing anything the day the pin was bumped (2026-08-03).
    from shared import llm_models
    _future = "claude-opus-99"
    assert _future != llm_models.OPUS_PIN, "fixture must differ from the live pin"
    got = mr.stale_tier_pins({"opus": _future}, {"opus": _dt(45)})
    assert len(got) == 1
    tier, pin, served, days = got[0]
    assert (tier, pin, served) == ("opus", llm_models.OPUS_PIN, _future)
    assert days == 45


def test_stale_tier_pins_never_dates_drift_it_cannot_date():
    """No changed_at (first-ever record) or an unparseable one must NOT be
    reported — a guessed age would be fabricated evidence."""
    assert mr.stale_tier_pins({"opus": "claude-opus-99"}, {}) == []
    assert mr.stale_tier_pins({"opus": "claude-opus-99"}, {"opus": "not-a-date"}) == []


def _seed_cache(tmp_path, resolved, changed_at):
    """Write a prior resolution cache so the refresh has a real 'previous'."""
    from shared.model_resolver import write_cache
    return write_cache(resolved, changed_at, cache_path=tmp_path / "cache.json")


def test_refresh_pin_drift_is_SILENT_between_monthly_boundaries(monkeypatch, tmp_path):
    """Throttled 2026-07-31 (/simplify efficiency finding): the audit row used to
    be ungated, so once a pin drifted it inserted one row per stale tier per
    weekday FOREVER, each restating an identical fact. Both the row and the nudge
    now fire only on the monthly boundary. Day 45 is between boundaries -> silence.
    """
    audit, tg = AsyncMock(), AsyncMock()
    _seed_cache(tmp_path, {"opus": "claude-opus-5"}, {"opus": _dt(45)})
    _mock_refresh_deps(monkeypatch, tmp_path, LIVE_IDS, audit=audit, telegram=tg)

    _run(mr.refresh_model_resolution())

    assert [c for c in audit.await_args_list if c.args[0] == "model_pin_drift"] == []
    tg.assert_not_awaited()


def test_refresh_pin_drift_nudges_on_the_monthly_boundary(monkeypatch, tmp_path):
    """Day 60 IS a multiple of 30 -> the Telegram nudge renders. Pins the text
    the operator would actually receive, including that it says there is no live
    impact (bindings resolve at boot; only a models.list outage serves the pin).
    """
    from shared import llm_models
    audit, tg = AsyncMock(), AsyncMock()
    # The refresh RECOMPUTES the tier from the available ids, so the drift this test asserts only
    # exists if the catalogue offers something NEWER than the committed pin. Pinning the fixture to
    # a real id made it silently stop testing anything the day OPUS_PIN was bumped to opus-5
    # (2026-08-03) — served then equalled the pin and no drift could occur. A hypothetical future
    # id keeps this about the MECHANISM rather than about today's pin value.
    _ids = LIVE_IDS + ["claude-opus-99"]
    _seed_cache(tmp_path, {"opus": "claude-opus-99"}, {"opus": _dt(60)})
    _mock_refresh_deps(monkeypatch, tmp_path, _ids, audit=audit, telegram=tg)

    _run(mr.refresh_model_resolution())

    # the guardrail must be able to SPEAK — in production this branch first runs
    # ~30 days after a release, so nothing else proves it works
    drift = [c for c in audit.await_args_list if c.args[0] == "model_pin_drift"]
    assert len(drift) == 1, "the pin-drift audit row never fired"
    assert llm_models.OPUS_PIN in drift[0].args[1] and "60d behind" in drift[0].args[1]
    tg.assert_awaited_once()
    text = tg.await_args.args[0]
    assert "OPUS_PIN" in text and llm_models.OPUS_PIN in text and "claude-opus-5" in text
    assert "No live impact" in text


def test_refresh_is_silent_about_pins_that_are_current(monkeypatch, tmp_path):
    """No drift when the served id IS the pin — the guardrail must not cry wolf
    on the normal state, or its one real firing gets ignored."""
    from shared import llm_models
    audit, tg = AsyncMock(), AsyncMock()
    ids = [llm_models.OPUS_PIN, llm_models.SONNET_PIN, llm_models.HAIKU_PIN]
    _seed_cache(tmp_path, dict(llm_models._TIER_PINS),
                {t: _dt(400) for t in llm_models._TIER_PINS})
    _mock_refresh_deps(monkeypatch, tmp_path, ids, audit=audit, telegram=tg)

    _run(mr.refresh_model_resolution())

    assert [c for c in audit.await_args_list if c.args[0] == "model_pin_drift"] == []
    tg.assert_not_awaited()


# ─── message shape (operator 2026-07-31: "could use some better formatting") ──

def test_transitions_group_by_version_not_one_line_per_role():
    """The complaint: 11 roles moving between the SAME two versions rendered as
    11 near-identical SCREAMING_SNAKE lines. One block per transition instead."""
    changes = [(f"R{i}_MODEL", "claude-sonnet-4-6", "claude-sonnet-5") for i in range(9)]
    changes.append(("JUDGE_MODEL", "claude-opus-4-8", "claude-opus-5"))
    out = "\n".join(mr._render_transitions(changes))
    assert out.count("Sonnet 4.6 → Sonnet 5") == 1, "sonnet block rendered more than once"
    assert out.count("Opus 4.8 → Opus 5") == 1
    assert "claude-sonnet-5" not in out and "_MODEL" not in out


def test_strongest_tier_is_listed_first():
    """The judge moves the grade surface — it must not sit under nine sonnet roles."""
    out = mr._render_transitions([
        ("THEME_MODEL", "claude-sonnet-4-6", "claude-sonnet-5"),
        ("JUDGE_MODEL", "claude-opus-4-8", "claude-opus-5"),
    ])
    joined = "\n".join(out)
    assert joined.index("Opus") < joined.index("Sonnet")


def test_unlabelled_role_renders_readably_never_blank():
    """A role added later without a label must degrade, not vanish or crash."""
    out = "\n".join(mr._render_transitions([
        ("SOME_FUTURE_MODEL", "claude-opus-4-8", "claude-opus-5")]))
    assert "some future" in out
