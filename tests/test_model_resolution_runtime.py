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
  5. check_judge_eval_divergence: match -> silent; mismatch -> ONE notice per change, no eval ask (audit +
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
    monkeypatch.setenv("APOLLO_LLM_SAMPLE_DIR", str(tmp_path / "samples"))   # no replay samples

    async def fake_list_ids():
        return list(ids)
    monkeypatch.setattr(mr, "_list_model_ids", fake_list_ids)
    audit_mock = audit if audit is not None else AsyncMock()
    monkeypatch.setattr(mr, "log_audit_event", audit_mock)
    tg_mock = telegram if telegram is not None else AsyncMock()
    monkeypatch.setattr(mr, "_send_telegram", tg_mock)
    # The pre-adoption canary (2026-09-23) makes real API calls through the factory; these
    # tests are about the resolver's bookkeeping, so every release passes here. The canary's
    # own adopt/refuse paths are pinned in tests/test_model_compat_adapter.py.
    monkeypatch.setattr(mr, "_canary_model", AsyncMock(return_value=(True, "")))
    monkeypatch.setattr(mr, "audit_event_exists", AsyncMock(return_value=False))
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
    # #690: ONE Telegram per tier adoption (opus AND sonnet move in LIVE_IDS), each carrying that
    # tier's replay digest — so two messages here, and the judge callout lives in the opus one.
    assert tg_mock.await_count == 2
    texts = [c.args[0] for c in tg_mock.await_args_list]
    text = next(t for t in texts if "Opus 4.8 → Opus 5" in t)
    assert "claude-opus-5" not in text
    # the callout is still RESOLVED_ROLES-driven, but named in plain words
    assert "grading judge" in text and "JUDGE_MODEL" not in text
    # 2026-09-22 — the EVAL caveat is GONE, by his ruling, and the notice itself is kept:
    # "I want to keep it to notify me when a model is updated, just not the eval." It now states
    # the no-eval rule and names the real guardrail instead. Pinned both ways, so the eval ask
    # cannot quietly come back in a later rewording.
    assert "No eval for a routine release" in text
    assert "grades HIGH" in text, "the notice no longer names the guardrail that replaced the eval"
    for banned in ("re-run the eval", "robustness eval", "did not cover", "accept it as-is"):
        assert banned not in text, f"the model-change notice is asking for an eval again: {banned!r}"
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


def _no_prior_notice(monkeypatch, rows=None):
    """The dedupe reads its own prior audit rows; default to 'never announced'."""
    import agents.market_intelligence.db as db
    async def _fake(event_type, summary):
        return any(r.get("summary") == summary for r in (rows or []))
    monkeypatch.setattr(db, "audit_event_exists", _fake)


def test_divergence_notifies_never_blocks_on_mismatch(monkeypatch, tmp_path):
    """A new model on the judge is still ANNOUNCED — he kept the notice (2026-09-22)."""
    _no_prior_notice(monkeypatch)
    audit_mock, tg_mock = _mock_divergence_deps(
        monkeypatch, tmp_path, {"judge_model": "claude-opus-4-8"}, running="claude-opus-5")
    _run(mr.check_judge_eval_divergence())  # must not raise — a notice, never a block
    audit_mock.assert_awaited_once()
    assert audit_mock.await_args.args[0] == "judge_model_eval_divergence"
    tg_mock.assert_awaited_once()
    text = tg_mock.await_args.args[0]
    assert "claude-opus-5" in text and "claude-opus-4-8" in text


def test_the_notice_never_asks_for_an_eval(monkeypatch, tmp_path):
    """⚠ HIS RULING, pinned as a negative. 2026-07-30: track the newest model per tier with
    guardrails after the switch. 2026-09-22, when Opus 5 -> 5.5 was announced and an eval was
    proposed: "Why eval? This is just normal model update, I thought we decided not to eval on
    model updates as that happens often." Then: "keep it to notify me when a model is updated,
    just not the eval." This notice used to say "Run the judge robustness eval to confirm
    quality (then bump JUDGE's pin)". It must never ask again — and it must say how to roll back,
    because that one edit is what makes tracking-without-an-eval safe."""
    _no_prior_notice(monkeypatch)
    audit_mock, tg_mock = _mock_divergence_deps(
        monkeypatch, tmp_path, {"judge_model": "claude-opus-5"}, running="claude-opus-5-5")
    _run(mr.check_judge_eval_divergence())
    text = tg_mock.await_args.args[0]
    for banned in ("robustness eval", "run the eval", "re-run", "confirm quality", "UNEVALUATED"):
        assert banned.lower() not in text.lower(), f"the notice is asking for an eval again: {banned!r}"
    assert "_TIER_OVERRIDES" in text, "the notice lost its one-edit rollback"
    detail = audit_mock.await_args.args[2]
    assert "run the judge robustness eval" not in detail, "the audit row still demands an eval"


def test_the_same_change_is_announced_ONCE_not_every_weeknight(monkeypatch, tmp_path):
    """⚠ THE NAG THIS FIXES. The check runs every weeknight at 6:09 PM and had no dedupe. With no
    eval ever re-run (his rule), the pass record never moves — so from the day a release binds it
    would have paged him EVERY WEEKNIGHT indefinitely. The second run for the same pair must be
    silent. Remove the dedupe and this fails on the second Telegram."""
    rows: list = []
    import agents.market_intelligence.db as db

    async def _fake(event_type, summary):
        return any(r["event_type"] == event_type and r["summary"] == summary for r in rows)
    monkeypatch.setattr(db, "audit_event_exists", _fake)

    async def _record(event_type, summary, detail="", **kw):
        rows.append({"event_type": event_type, "summary": summary})
    tg_mock = AsyncMock()
    _mock_divergence_deps(monkeypatch, tmp_path, {"judge_model": "claude-opus-5"},
                          running="claude-opus-5-5", audit=AsyncMock(side_effect=_record),
                          telegram=tg_mock)
    _run(mr.check_judge_eval_divergence())   # night 1 — announces
    _run(mr.check_judge_eval_divergence())   # night 2 — same pair, must stay quiet
    _run(mr.check_judge_eval_divergence())   # night 3
    assert tg_mock.await_count == 1, (
        f"the same model change paged {tg_mock.await_count} times — it is a nightly nag again"
    )


def test_a_NEW_release_is_announced_again(monkeypatch, tmp_path):
    """Once per change, not once ever: the NEXT release is a new pair and must be announced."""
    _no_prior_notice(monkeypatch, rows=[
        {"summary": "JUDGE_MODEL now on claude-opus-5-5; last evaluated model claude-opus-5"}])
    _, tg_mock = _mock_divergence_deps(
        monkeypatch, tmp_path, {"judge_model": "claude-opus-5"}, running="claude-opus-6")
    _run(mr.check_judge_eval_divergence())
    tg_mock.assert_awaited_once()


def test_a_failed_dedupe_lookup_SENDS_rather_than_goes_silent(monkeypatch, tmp_path):
    """His guardrail #2: a model change is a NOTIFIED event, never silent. If the dedupe read
    breaks, the direction is 'send a duplicate', never 'drop the change'."""
    import agents.market_intelligence.db as db

    async def _boom(event_type, summary):
        raise RuntimeError("db down")
    monkeypatch.setattr(db, "audit_event_exists", _boom)
    _, tg_mock = _mock_divergence_deps(
        monkeypatch, tmp_path, {"judge_model": "claude-opus-5"}, running="claude-opus-5-5")
    _run(mr.check_judge_eval_divergence())
    tg_mock.assert_awaited_once()


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
    _no_prior_notice(monkeypatch)
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


# ─── #690 pre-adoption replay of our own requests + per-role holds ───────────
# Fake SDK client behind the REAL transport adapter (wrap_client); samples written as the capture
# writes them, under REAL call-site keys, so the role comes from the committed call-site map.

from types import SimpleNamespace  # noqa: E402

from shared import llm_samples  # noqa: E402
from shared.llm_client import wrap_client  # noqa: E402

THEME_KEY = "agents.market_intelligence.theme_engine:_rename_theme_to_fit_cluster"   # THEME_MODEL
GRADE_KEY = "agents.market_intelligence.ep_detector:_classify_catalyst_claude"        # GROUNDED_GRADE_MODEL
GRADE_TOOL = {"name": "grade_catalyst", "input_schema": {
    "type": "object", "required": ["quality"],
    "properties": {"quality": {"type": "string"}, "analysis": {"type": "string"}}}}
OLD, NEW = "claude-sonnet-5", "claude-sonnet-5-5"


class _Block:
    def __init__(self, type, **kw):
        self.type = type
        for k, v in kw.items():
            setattr(self, k, v)


class _Resp:
    def __init__(self, content, stop_reason="end_turn", model=NEW):
        self.content, self.stop_reason, self.model = content, stop_reason, model
        self.usage = SimpleNamespace(input_tokens=1, output_tokens=1,
                                     cache_creation_input_tokens=0, cache_read_input_tokens=0)

    def model_copy(self, update=None):
        new = _Resp(self.content, self.stop_reason, self.model)
        for k, v in (update or {}).items():
            setattr(new, k, v)
        return new


class _Http(Exception):
    def __init__(self, status, message="boom"):
        super().__init__(message)
        self.status_code, self.message = status, message


class _ReplayFake:
    def __init__(self, behaviour):
        self.behaviour, self.calls = behaviour, []

    async def create(self, **kw):
        self.calls.append(kw)
        return self.behaviour(kw)


def _grade_answer(quality="high", analysis="a different paragraph of reasoning"):
    return _Resp([_Block("tool_use", id="t", name="grade_catalyst",
                         input={"quality": quality, "analysis": analysis})], "tool_use")


def _is_theme(kw):
    return "theme" in json.dumps(kw["messages"])


def _write_sample(tmp_path, key, role, *, model=OLD, request=None, answer=None, subject=""):
    d = tmp_path / "samples"
    d.mkdir(exist_ok=True)
    data = {"schema": 1, "key": key, "role": role, "skipped": {}, "samples": [{
        "captured_at": "2026-09-29T20:00:00+00:00", "model": model, "role": role,
        "replayable": True, "request": request, "answer": answer, "subject": subject}]}
    llm_samples._file_for(key, d).write_text(json.dumps(data), encoding="utf-8")


def _theme_and_grade_samples(tmp_path, *, grade_quality="moderate"):
    _write_sample(tmp_path, THEME_KEY, "THEME_MODEL",
                  request={"model": OLD, "max_tokens": 400,
                           "messages": [{"role": "user", "content": "rename this theme"}]},
                  answer={"stop_reason": "end_turn", "text": "AI Networking"})
    _write_sample(tmp_path, GRADE_KEY, "GROUNDED_GRADE_MODEL", subject="ABCD",
                  request={"model": OLD, "max_tokens": 900, "tools": [GRADE_TOOL],
                           "tool_choice": {"type": "tool", "name": "grade_catalyst"},
                           "messages": [{"role": "user", "content": "Ticker: ABCD grade it"}]},
                  answer={"stop_reason": "tool_use", "tool": "grade_catalyst",
                          "tool_input": {"quality": grade_quality, "analysis": "old reasoning"}})


def _replay_refresh(monkeypatch, tmp_path, behaviour, *, resolved=None, holds=None, ids=None):
    from shared.model_resolver import write_cache
    cache = tmp_path / "cache.json"
    monkeypatch.setenv("APOLLO_MODEL_RESOLUTION_CACHE", str(cache))
    monkeypatch.setenv("APOLLO_LLM_SAMPLE_DIR", str(tmp_path / "samples"))
    write_cache(resolved or {"opus": "claude-opus-5-5", "sonnet": OLD,
                             "haiku": "claude-haiku-4-5-20251001"},
                {}, cache_path=cache, role_holds=holds)
    listing = ids or ["claude-opus-5-5", NEW, OLD, "claude-haiku-4-5-20251001"]
    monkeypatch.setattr(mr, "_list_model_ids", AsyncMock(return_value=list(listing)))
    monkeypatch.setattr(mr, "_canary_model", AsyncMock(return_value=(True, "")))
    monkeypatch.setattr(mr, "audit_event_exists", AsyncMock(return_value=False))
    audit, tg = AsyncMock(), AsyncMock()
    monkeypatch.setattr(mr, "log_audit_event", audit)
    monkeypatch.setattr(mr, "_send_telegram", tg)
    fake = _ReplayFake(behaviour)
    monkeypatch.setattr(mr, "_replay_client", lambda: wrap_client(SimpleNamespace(messages=fake)))
    monkeypatch.setattr(mr, "_log_replay_spend", AsyncMock())
    return audit, tg, fake, cache


def _events(audit):
    return [c.args[0] for c in audit.await_args_list]


def test_a_refusing_role_is_held_while_the_tier_moves_for_the_others(monkeypatch, tmp_path):
    """(a) The 2026-09-28 shape: the new sonnet refuses our theme prompts. THEME_MODEL is HELD on
    Sonnet 5, the tier still moves for every other role, and the Telegram names the hold."""
    from shared.model_resolver import read_cache
    _theme_and_grade_samples(tmp_path, grade_quality="high")
    audit, tg, fake, cache = _replay_refresh(
        monkeypatch, tmp_path,
        lambda kw: _Resp([], "refusal") if _is_theme(kw) else _grade_answer("high"))
    _run(mr.refresh_model_resolution())

    data = read_cache(cache)
    assert data["resolved"]["sonnet"] == NEW                           # adopted for the others
    hold = data["role_holds"]["THEME_MODEL"]
    assert hold["model"] == OLD and hold["candidate"] == NEW and hold["error"] == "refused"
    assert set(data["role_holds"]) == {"THEME_MODEL"}                  # the grader is NOT held
    assert len(fake.calls) == 2 * mr.REPLAY_RUNS and {c["model"] for c in fake.calls} == {NEW}
    assert "model_role_held" in _events(audit) and "model_replay_digest" in _events(audit)

    text = tg.await_args.args[0]
    assert "New Claude model available" in text and "Sonnet 5 → Sonnet 5.5" in text
    assert "theme discovery: <b>HELD</b> on Sonnet 5 — refused" in text
    assert "catalyst grading: 1 same" in text
    assert "next deploy or restart" in text

    # at the next boot the hold is what THEME_MODEL binds to; its neighbours take the new model
    assert llm_models._resolve_for("THEME_MODEL", "sonnet", cache).model == OLD
    assert llm_models._resolve_for("GROUNDED_GRADE_MODEL", "sonnet", cache).model == NEW


def test_a_changed_decision_is_reported_never_held(monkeypatch, tmp_path):
    """(b) Every run answers; the grade's quality moved moderate → high. Adopted, nothing held,
    and the digest names the change — the free-text analysis is NOT compared."""
    from shared.model_resolver import read_cache
    _theme_and_grade_samples(tmp_path, grade_quality="moderate")
    audit, tg, fake, cache = _replay_refresh(
        monkeypatch, tmp_path,
        lambda kw: _Resp([_Block("text", text="AI Infra")]) if _is_theme(kw) else _grade_answer("high"))
    _run(mr.refresh_model_resolution())
    data = read_cache(cache)
    assert data["resolved"]["sonnet"] == NEW and data["role_holds"] == {}
    text = tg.await_args.args[0]
    assert "catalyst grading: 1 changed (quality moderate → high on ABCD)" in text
    assert "analysis" not in text
    assert "theme discovery: 1 text answer, not compared" in text
    detail = next(c.args[2] for c in audit.await_args_list if c.args[0] == "model_replay_digest")
    assert json.loads(detail)["keys"][0]["runs"][0]["verdict"] == "pass"


def test_an_unfinished_replay_adopts_nothing_on_that_tier(monkeypatch, tmp_path):
    """(c) The budget runs out before the tier's requests are judged: the tier keeps its old id
    tonight, an audit row is written and the operator is told once."""
    from shared.model_resolver import read_cache
    _theme_and_grade_samples(tmp_path)
    monkeypatch.setattr(mr, "REPLAY_BUDGET_S", 0.0)
    audit, tg, fake, cache = _replay_refresh(monkeypatch, tmp_path, lambda kw: _grade_answer())
    _run(mr.refresh_model_resolution())
    data = read_cache(cache)
    assert data["resolved"]["sonnet"] == OLD and "sonnet" not in data["changed_at"]
    assert data["role_holds"] == {}
    assert fake.calls == []
    assert "model_replay_budget_exhausted" in _events(audit)
    assert "model_release_detected" not in _events(audit)
    tg.assert_awaited_once()
    assert "not adopted tonight" in tg.await_args.args[0]


def test_the_budget_alert_is_sent_once_not_nightly(monkeypatch, tmp_path):
    _theme_and_grade_samples(tmp_path)
    monkeypatch.setattr(mr, "REPLAY_BUDGET_S", 0.0)
    audit, tg, _fake, _cache = _replay_refresh(monkeypatch, tmp_path, lambda kw: _grade_answer())
    monkeypatch.setattr(mr, "audit_event_exists", AsyncMock(return_value=True))
    _run(mr.refresh_model_resolution())
    tg.assert_not_awaited()
    assert "model_replay_budget_exhausted" in _events(audit)          # the row is still written


def test_a_held_role_is_released_once_its_requests_pass(monkeypatch, tmp_path):
    """(d) Next night, no new release: the held role's own requests are replayed on the tier's
    model, pass, and the hold is released (Telegram + audit)."""
    from shared.model_resolver import read_cache
    _write_sample(tmp_path, THEME_KEY, "THEME_MODEL",
                  request={"model": OLD, "max_tokens": 400,
                           "messages": [{"role": "user", "content": "rename this theme"}]},
                  answer={"stop_reason": "end_turn", "text": "AI Networking"})
    held = {"THEME_MODEL": {"model": OLD, "since": "2026-09-29T22:08:00+00:00",
                            "error": "refused", "candidate": NEW}}
    audit, tg, fake, cache = _replay_refresh(
        monkeypatch, tmp_path, lambda kw: _Resp([_Block("text", text="AI Networking")]),
        resolved={"opus": "claude-opus-5-5", "sonnet": NEW, "haiku": "claude-haiku-4-5-20251001"},
        holds=held)
    _run(mr.refresh_model_resolution())
    assert read_cache(cache)["role_holds"] == {}
    assert {c["model"] for c in fake.calls} == {NEW} and len(fake.calls) == mr.REPLAY_RUNS
    assert "model_role_hold_released" in _events(audit)
    tg.assert_awaited_once()
    text = tg.await_args.args[0]
    assert "hold released" in text.lower() and "theme discovery" in text and "Sonnet 5.5" in text


def test_a_held_role_that_still_fails_stays_held_quietly(monkeypatch, tmp_path):
    from shared.model_resolver import read_cache
    _write_sample(tmp_path, THEME_KEY, "THEME_MODEL",
                  request={"model": OLD, "max_tokens": 400,
                           "messages": [{"role": "user", "content": "rename this theme"}]},
                  answer={"stop_reason": "end_turn", "text": "AI Networking"})
    held = {"THEME_MODEL": {"model": OLD, "since": "2026-09-29T22:08:00+00:00",
                            "error": "refused", "candidate": NEW}}
    audit, tg, _fake, cache = _replay_refresh(
        monkeypatch, tmp_path, lambda kw: _Resp([], "refusal"),
        resolved={"opus": "claude-opus-5-5", "sonnet": NEW, "haiku": "claude-haiku-4-5-20251001"},
        holds=held)
    _run(mr.refresh_model_resolution())
    kept = read_cache(cache)["role_holds"]["THEME_MODEL"]
    assert kept["model"] == OLD and kept["since"] == "2026-09-29T22:08:00+00:00"
    tg.assert_not_awaited()
    assert "model_role_hold_released" not in _events(audit)


def test_rate_limits_are_unjudged_never_a_hold(monkeypatch, tmp_path):
    from shared.model_resolver import read_cache
    _theme_and_grade_samples(tmp_path)

    def always_429(kw):
        raise _Http(429, "rate_limit_error")
    audit, tg, fake, cache = _replay_refresh(monkeypatch, tmp_path, always_429)
    _run(mr.refresh_model_resolution())
    data = read_cache(cache)
    assert data["resolved"]["sonnet"] == NEW and data["role_holds"] == {}
    assert len(fake.calls) == 2 * mr.REPLAY_RUNS * 2                   # each run retried once
    assert "could not be checked (HTTP 429 (twice))" in tg.await_args.args[0]


def test_a_4xx_after_the_adapter_holds_the_role(monkeypatch, tmp_path):
    from shared.model_resolver import read_cache
    _theme_and_grade_samples(tmp_path)

    def grade_rejected(kw):
        if _is_theme(kw):
            return _Resp([_Block("text", text="ok")])
        raise _Http(400, "prompt is too long")
    _audit, _tg, _fake, cache = _replay_refresh(monkeypatch, tmp_path, grade_rejected)
    _run(mr.refresh_model_resolution())
    hold = read_cache(cache)["role_holds"]["GROUNDED_GRADE_MODEL"]
    assert hold["error"].startswith("rejected (HTTP 400)")


def test_only_samples_recorded_on_the_tiers_current_model_are_replayed(monkeypatch, tmp_path):
    _write_sample(tmp_path, THEME_KEY, "THEME_MODEL", model="claude-sonnet-4-6",
                  request={"model": "claude-sonnet-4-6", "max_tokens": 50,
                           "messages": [{"role": "user", "content": "rename this theme"}]},
                  answer={"stop_reason": "end_turn", "text": "x"})
    _audit, tg, fake, _cache = _replay_refresh(monkeypatch, tmp_path, lambda kw: _Resp([], "refusal"))
    _run(mr.refresh_model_resolution())
    assert fake.calls == []
    assert "no recent request to replay" in tg.await_args.args[0]


def test_role_is_held_is_any_failure_and_nothing_else():
    R = mr.RunResult
    assert mr.role_is_held([R(mr.PASS), R(mr.FAIL, "refused"), R(mr.PASS)])
    assert not mr.role_is_held([R(mr.PASS), R(mr.UNJUDGED, "HTTP 529 (twice)"), R(mr.PASS)])
    assert not mr.role_is_held([])


def test_decision_diff_compares_decisions_not_prose():
    old = {"tool": "t", "tool_input": {"tier": "MODERATE", "grade": 70, "direct": True,
                                       "tags": ["b", "a"], "rationale": "x",
                                       "headline": "y" * 60}}
    new = {"tool": "t", "tool_input": {"tier": "HIGH", "grade": 70.0, "direct": True,
                                       "tags": ["a", "b"], "rationale": "z",
                                       "headline": "w" * 60}}
    assert mr.decision_diff(old, new) == ("changed", ["tier MODERATE → HIGH"])
    assert mr.decision_diff(old, old) == ("same", [])
    assert mr.decision_diff({"text": "a"}, {"text": "b"}) == ("text", [])
    assert mr.decision_diff(old, {"tool": "other", "tool_input": {}})[1] == ["tool t → other"]
