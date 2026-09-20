"""#662 — the weekly system review is an ACTION head over a folded detail body.

Operator 2026-09-14: *"the review today is info dense data dense but most weeks there's not much
action, let's make it high signal so I can actually read it and it highlights action for us."*
The 2026-09-20 edition proved the case three times over: three "silent failures" that were all
already dealt with, a promotion blocker that can never clear printed as "deferred", and a
live-vs-calibration block that pooled 28 trades under old exit rules with 2 under the current
one. Every rule below is a presentation rule — no metric, threshold or verdict moved.

Each test names the mutation that reddened it; each was run RED against that mutation and
restored green before this file was committed.
"""
from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

import agents.market_intelligence.kill_scale_bands as ksb
import agents.market_intelligence.replay_regression as rr
import agents.market_intelligence.system_review as sr
from agents.market_intelligence.rule_eras import split_current_vs_older
from agents.market_intelligence.strategies.promotion import MANUAL_REVIEW_HOLD_REASON
from shared.telegram_format import chunk_html, md_to_html

TODAY = date(2026, 9, 20)
NOW = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)       # 08:00 ET, the Sunday run


def _meta(n: int, d: date = date(2026, 8, 20), sig: str = "magna53") -> list[dict]:
    return [{"alert_date": d, "signal_type": sig} for _ in range(n)]


def _inputs(rs, meta=None):
    out = {"realized_rs": rs, "drawdown_tier": "OK", "equity_above_start": False,
           "account_mode": "live", "open_positions": []}
    if meta is not None:
        out["realized_r_meta"] = meta
    return out


# ── the head/fold split ──────────────────────────────────────────────────────────────────────

def test_quiet_week_opens_with_one_sentence_and_fits_a_phone():
    """MUTATION: `if not n_you and not n_me:` → `if False:` in `compose_report` — the sentence
    vanished and the head printed empty action headers. RED, restored."""
    head, fold, meta = sr.compose_report(
        "🧠 *Weekly review — Sep 13–20* · regime Correcting", [], [],
        ["errors: none", "bands: HOLD", "spend: $25.65 of $150"],
        ["✅ *Working*\n• three bullets", "🎯 *MFE capture* 19%"], [])
    lines = head.splitlines()
    assert lines[1] == "*Nothing needs you this week.*"
    assert meta["head_lines"] <= 4                      # header · sentence · checked line
    assert "Also checked" in lines[-1] and "bands: HOLD" in lines[-1]
    assert "MFE capture" not in head and "MFE capture" in fold
    assert meta["needs_you"] == 0 and meta["needs_me"] == 0


def test_every_action_item_sits_above_every_counter():
    """MUTATION: `render_review_html` emitted the fold BEFORE the head — the action lines
    landed under the counters. RED, restored."""
    head, fold, meta = sr.compose_report(
        "🧠 *Weekly review*",
        [(2, "📅 *Reviews ready* (2)\n🔴 *old one* _[ripe 56d]_\n• *new one* _[ripe 3d]_")],
        ["nightly_data_pull: cancelled (Sat 09-19 00:16 ET) — no re-run in the job ledger"],
        ["errors: 1 row, 1 open (above)"],
        ["⚖️ *Holistic judge* Graded 5/5", "*🔁 Replay-regression* live (n=30)"], [])
    assert head.index("*Needs you (2):*") < head.index("🔴 *old one*") < head.index("*Needs me (1):*")
    assert "Holistic judge" not in head and "Replay-regression" not in head
    html = sr.render_review_html(head, fold)
    assert html.index("old one") < html.index("nightly_data_pull") < html.index("<blockquote expandable>")
    assert html.index("<blockquote expandable>") < html.index("Holistic judge")
    assert meta["needs_you"] == 2 and meta["needs_me"] == 1
    assert meta["needs_you_lines"] == ["🔴 *old one* _[ripe 56d]_", "• *new one* _[ripe 3d]_"]


def test_fold_is_an_expandable_quote_carrying_no_code_markup():
    """Telegram's nesting rule: pre/code cannot sit inside another entity, and the fold IS a
    blockquote entity — a 400 there makes the sender fall back to plain text, i.e. the
    unfolded dump. MUTATION: the `_strip_code_markup` call removed from `render_review_html`
    — `<pre>` appeared inside the quote. RED, restored."""
    fold = "🧪 *Setup review*\n```\nmagna53/live n=30\n```\n_see `judge_delta_review.py`_"
    html = sr.render_review_html("*head* line", fold)
    head_html, quote = html.split("\n<blockquote expandable>", 1)
    assert head_html == md_to_html("*head* line")
    assert quote.endswith("</blockquote>")
    assert "<pre>" not in quote and "<code>" not in quote
    assert "magna53/live n=30" in quote and "judge_delta_review.py" in quote
    assert "<b>Setup review</b>" in quote                   # bold survives inside the quote
    # a split never leaves the quote open in one chunk and closed in the next
    long_html = sr.render_review_html("*head*", "\n\n".join(f"section {i} " + "x" * 300 for i in range(30)))
    for chunk in chunk_html(long_html):
        assert chunk.count("<blockquote expandable>") == chunk.count("</blockquote>")


# ── silent failures: an item the system has recorded as dealt with is not an open anomaly ──

def _err(event_type, detail, hours_ago, summary="x"):
    return {"event_type": event_type, "summary": summary, "detail": detail,
            "created_at": NOW - timedelta(hours=hours_ago)}


def _run_errors(monkeypatch, rows, ledger):
    async def _audit(limit=500, since_hours=48, event_type=None, event_type_like=None):
        pat = (event_type_like or "").replace("%", "")
        return [r for r in rows if pat in r["event_type"]]
    monkeypatch.setattr(sr, "get_audit_log", _audit)
    monkeypatch.setattr(sr, "get_job_runs_for", AsyncMock(return_value=ledger))
    monkeypatch.setattr(sr, "_utcnow", lambda: NOW)
    return asyncio.run(sr._aggregate_audit_errors(7))


def test_a_send_the_probe_muzzle_refused_on_purpose_is_not_open(monkeypatch):
    """The 2026-09-20 fourth row: `scripts/probes/_muzzle` REFUSED a send and the sender logged
    it as telegram_send_failed. MUTATION: `if exc == _REFUSED_MARKER` → `if False` in
    `_dispose_error_row` — the refusal read as a live failure. RED, restored."""
    from scripts.probes._muzzle import TelegramSendRefused
    assert sr._REFUSED_MARKER == TelegramSendRefused.__name__   # a rename breaks HERE, loudly
    out = _run_errors(monkeypatch, [
        _err("telegram_send_failed",
             "TelegramSendRefused: refused a send to api.telegram.org (captured #1) | chat=1 | first_chunk=⚠️",
             hours_ago=1, summary="Telegram send exception")], [])
    t = out["top_types"][0]
    assert t["disposition"] == "refused" and t["open"] is False
    assert out["open_total"] == 0
    assert "probe muzzle" in out["dispositioned"][0]["rule"]


def test_job_failures_are_dispositioned_from_the_ledger_and_only_the_unrecorded_stay_open(monkeypatch):
    """Four job-class rows, one ledger: A re-ran clean → recovered; B was hand-closed by the
    operator (#672 `unrecoverable`) → closed; C has nothing recorded and is a day old → live;
    D has nothing recorded but went quiet 5 days ago → quiet. MUTATION: `clean = None`
    forced in `_dispose_error_row` — A read as live and open_total became 2. RED, restored."""
    def job_row(job_id, hours_ago):
        return _err("job_cancelled_error", json.dumps({"job_id": job_id, "rows_written": None}),
                    hours_ago, summary=f"{job_id}: cancelled — restart mid-run; outcome unknown")
    rows = [job_row("A", 30), job_row("B", 30), job_row("C", 20), job_row("D", 5 * 24)]
    ledger = [
        {"job_id": "A", "started_at": NOW - timedelta(hours=6), "status": "success", "error_message": None},
        {"job_id": "A", "started_at": NOW - timedelta(hours=40), "status": "success", "error_message": None},
        {"job_id": "B", "started_at": NOW - timedelta(hours=2), "status": "unrecoverable",
         "error_message": "operator 2026-09-20: forget Friday — slot closed by hand"},
    ]
    out = _run_errors(monkeypatch, rows, ledger)
    t = out["top_types"][0]
    by_job = {d["job_id"]: d for d in t["rows"]}
    assert by_job["A"]["disposition"] == "recovered" and "ran clean" in by_job["A"]["why"]
    assert by_job["B"]["disposition"] == "closed" and "closed by hand" in by_job["B"]["why"]
    assert by_job["C"]["disposition"] == "live"
    assert by_job["D"]["disposition"] == "quiet" and "not recurred in 5d" in by_job["D"]["why"]
    assert t["disposition"] == "live" and out["open_total"] == 1
    assert {s["what"].split(" at ")[0] for s in out["dispositioned"]} == {"job_cancelled_error"}
    assert len(out["dispositioned"]) == 3
    # the fold names every disposition; the head names only the open one
    fold = sr._format_silent_failures_section(out)
    assert "4 row(s), 1 open" in fold and "recovered: A ran clean" in fold
    assert fold.count("live:") == 1


# ── a check that cannot change state is not "pending" ───────────────────────────────────────

def test_a_hold_by_operator_ruling_is_never_printed_as_deferred():
    """wick_fill's blocker is appended unconditionally by `review_required: true` — no data can
    clear it (db.py registry seed, #424). MUTATION: the hold no longer filtered out of
    `reasons` in `_format_promotion_section` — the line read 'eligibility deferred' again.
    RED, restored."""
    text, held = sr._format_promotion_section({"checks": [
        {"strategy_id": "wick_fill", "current_phase": "shadow", "next_phase": "paper",
         "eligible": False, "metrics": {"fill_rate": 0.702, "n_candidates": 47},
         "blocking_reasons": [MANUAL_REVIEW_HOLD_REASON]},
        {"strategy_id": "shadow_orb_5m", "current_phase": "shadow", "next_phase": "paper",
         "eligible": False, "metrics": {"median_r": -0.1, "n_closed": 42},
         "blocking_reasons": ["median R -0.10113402106503139 < 0.0"]},
        {"strategy_id": "parabolic_short", "current_phase": "shadow", "next_phase": "paper",
         "eligible": False, "metrics": {"n_climax_alerts": 4},
         "blocking_reasons": ["need 20 climax_alerts (have 4)", MANUAL_REVIEW_HOLD_REASON]},
        {"strategy_id": "magna53", "current_phase": "live", "next_phase": None,
         "eligible": False, "metrics": {}, "blocking_reasons": ["already at top of ladder"]},
    ]})
    assert held == ["wick_fill"]
    assert "wick_fill: held in shadow by operator ruling" in text
    assert "deferred" not in text and "not yet captured" not in text
    assert "shadow_orb_5m: median R -0.10 < 0.0 (have 42 closed)" in text     # rounded, counted
    assert "parabolic_short: need 20 climax_alerts (have 4)" in text          # the data blocker leads
    assert "magna53" not in text                                              # top of ladder: silent


def test_an_eligible_strategy_is_his_sign_off_in_the_head(monkeypatch):
    """MUTATION: `ready = [...]` filter in `_assemble_report` dropped the `eligible` test — the
    held wick_fill surfaced as 'ready to move'. RED, restored."""
    head, fold, meta = _assemble(monkeypatch, strategy_promotions={"checks": [
        {"strategy_id": "shadow_orb_5m", "current_phase": "shadow", "next_phase": "paper",
         "eligible": True, "metrics": {"n_closed": 42}, "blocking_reasons": []},
        {"strategy_id": "wick_fill", "current_phase": "shadow", "next_phase": "paper",
         "eligible": False, "metrics": {}, "blocking_reasons": [MANUAL_REVIEW_HOLD_REASON]},
    ]})
    assert "*Needs you (1):*" in head
    assert "strategy `shadow_orb_5m` is ready to move shadow → paper — your sign-off" in head
    assert "wick_fill" not in head
    assert {"what": "wick_fill promotion blocker",
            "rule": "held by operator ruling — no data can change it, so it is not pending"} in meta["suppressed"]


# ── ripe-review age is a first-class alarm, and age is not the whole story ──────────────────

def test_a_stale_ripe_review_leads_with_the_alarm_and_the_rule_changes_since_it_was_written():
    """MUTATION: `marker = "•"` forced in `_format_pending_reviews_section` — the 56-day item
    lost its 🔴. RED, restored."""
    ready = [
        {"review_id": "fresh", "title": "Fresh question", "kind": "accrual",
         "earliest_review_date": (TODAY - timedelta(days=5)).isoformat(),
         "action_when_ready": "Read the forward outcomes\nover two lines. Then more."},
        {"review_id": "stale", "title": "#354 ADR 0026 C5 — does the edge hold?", "kind": "accrual",
         "earliest_review_date": (TODAY - timedelta(days=56)).isoformat(), "added_on": "2026-07-19",
         "action_when_ready": "Re-run the round-1 readout. Then decide."},
    ]
    out = sr._format_pending_reviews_section({"ready": ready}, today=TODAY)
    lines = out.splitlines()
    assert lines[0].startswith("📅 *Reviews ready* (2)")
    assert "1 have been ripe ≥30d" in lines[1]
    assert lines[2].startswith("🔴 *#354 ADR 0026 C5") and "_[ripe 56d]_" in lines[2]
    assert "written 2026-07-19, 10 rule changes since (latest 2026-09-06)" in lines[2]
    assert "re-check the question against the live rule" in lines[2]
    assert lines[3].startswith("• *Fresh question*") and "_[ripe 5d]_" in lines[3]
    assert "Read the forward outcomes over two lines." in lines[3]      # one line per item
    assert len(lines) == 4


# ── every trailing-window number carries its era and its n, or it is suppressed ─────────────

def test_replay_regression_live_line_carries_the_era_split_or_is_suppressed():
    """MUTATION: the `elif era_split is None` branch removed from `render_section` — the
    pooled live numbers printed with no era clause. RED, restored."""
    rs = [-1.0, -1.0, 3.0, -1.0, -0.5]
    meta = _meta(3) + _meta(2, d=date(2026, 9, 8))          # 3 under older rules, 2 current
    fp = rr.compute_fingerprint(rs)
    with_split = "\n".join(rr.render_section("live", fp, split_current_vs_older(rs, meta, TODAY)))
    assert "live (n=5): exp -0.10R" in with_split
    assert "under the current rules (since 2026-09-06): 2 trades · older rules: 3 trades" in with_split
    assert "current rules n<5, no read" in with_split         # an era too thin to read says so
    suppressed = "\n".join(rr.render_section("live", fp, None))
    assert "live (n=5): numbers suppressed" in suppressed
    assert "exp -0.10R" not in suppressed
    assert "rule eras: UNAVAILABLE" in suppressed
    assert "calibration (#268b" in suppressed                  # the reference card still renders


def test_early_window_drift_and_band_lines_carry_the_era_clause(monkeypatch):
    """MUTATION: `era_split_sentence(split)` dropped from the `_early_window_drift_review`
    return — the rolling mean printed with no era. RED, restored."""
    rs = [-1.0, -1.0, 3.0, -1.0, -1.0, 0.5]
    meta = _meta(4) + _meta(2, d=date(2026, 9, 8))
    monkeypatch.setattr(ksb, "assemble_band_inputs", AsyncMock(return_value=_inputs(rs, meta)))
    text, suppressed = asyncio.run(sr._early_window_drift_review(TODAY))
    assert "rolling mean -0.08R over 6 closed trades" in text
    assert "under the current rules (since 2026-09-06): 2 trades · older rules: 4 trades" in text
    assert suppressed is None

    monkeypatch.setattr(ksb, "assemble_band_inputs", AsyncMock(return_value=_inputs(rs)))
    text, suppressed = asyncio.run(sr._early_window_drift_review(TODAY))
    assert "numbers suppressed" in text and "-0.08R" not in text
    assert suppressed["what"] == "early-window drift numbers"

    verdict = ksb.BandVerdict(band="HOLD", action="No change", reasons=["within bands"],
                              n_trades=6, trailing_20=-0.08, cum_r=-0.5)
    monkeypatch.setattr(ksb, "assess_bands", AsyncMock(return_value=(_inputs(rs, meta), verdict, None)))
    block, band, action = asyncio.run(sr._band_section(TODAY))
    assert band == "HOLD" and "*Kill/scale band: HOLD*" in block
    assert "rule eras: under the current rules (since 2026-09-06): 2 trades · older rules: 4 trades" in block


# ── the whole assembly ──────────────────────────────────────────────────────────────────────

def _assemble(monkeypatch, **overrides):
    """Drive `_assemble_report` with a quiet-week fixture; `overrides` replace metrics keys."""
    metrics = {
        "regime": {"current": "Correcting"},
        "pending_reviews": {"ready": [], "pending_count": 56},
        "audit_errors": {"total": 0, "open_total": 0, "top_types": [], "dispositioned": []},
        "strategy_promotions": {"checks": [
            {"strategy_id": "wick_fill", "current_phase": "shadow", "next_phase": "paper",
             "eligible": False, "metrics": {}, "blocking_reasons": [MANUAL_REVIEW_HOLD_REASON]}]},
        "crypto": {"verdict": "✅ live; gates clean", "shadow_mode": False, "universe_size": 331,
                   "rs_history_days": 135, "macro_history_days": 135, "ingest_attempts_7d": 6},
        "judge_weekly": {"total": 0}, "loser_breakdown": {}, "mfe_capture": {},
        "missed_opportunities": {},
    }
    metrics.update(overrides)
    monkeypatch.setattr(sr, "_setup_performance_review", AsyncMock(return_value=("", [])))
    monkeypatch.setattr(sr, "_spend_envelope", AsyncMock(return_value=("💵 *Cost envelope (MTD)*\nLLM: $25.65 / $150 (17%) ✓ · 3093 calls", 25.65, 150.0, False)))
    monkeypatch.setattr(sr, "_judge_divergence_section", AsyncMock(return_value=""))
    verdict = ksb.BandVerdict(band="HOLD", action="No change", reasons=["within bands"], n_trades=5)
    monkeypatch.setattr(ksb, "assess_bands",
                        AsyncMock(return_value=(_inputs([-1.0] * 5, _meta(5)), verdict, None)))
    monkeypatch.setattr(ksb, "assemble_band_inputs", AsyncMock(return_value=_inputs([-1.0] * 5, _meta(5))))
    monkeypatch.setattr(rr, "run_replay_regression",
                        AsyncMock(return_value={"lines": ["", "*🔁 Replay-regression* (live R-dist)", "  live (n=5)"]}))
    return asyncio.run(sr._assemble_report(metrics, "✅ *Working*\n• the narrator's bullets",
                                           TODAY - timedelta(days=7), TODAY))


def test_a_quiet_week_says_so_and_names_what_was_checked(monkeypatch):
    """The positive observable: a generator that silently skipped its sections could not print
    the 'Also checked' line naming each surface. MUTATION: `checked` list emptied before
    `compose_report` — the line vanished. RED, restored."""
    head, fold, meta = _assemble(monkeypatch)
    lines = head.splitlines()
    assert lines[0].startswith("🧠 *Weekly review — Sep 13–20* · regime Correcting")
    assert lines[1] == "*Nothing needs you this week.*"
    checked = lines[2]
    for phrase in ("reviews: 0 ripe, 56 still accruing", "errors: none",
                   "promotions: 0 ready, 0 accruing, 1 held by ruling", "bands: HOLD",
                   "crypto: live, gates clean", "spend: $25.65 of $150"):
        assert phrase in checked, phrase
    assert len(lines) == 3
    assert "the narrator's bullets" in fold                # UNVERIFIED narrative: fold, not head
    assert "📈 *Strategy promotion* — none ready" in fold
    assert "*🎚️ Kill/scale bands*" in fold and "rule eras:" in fold
    assert meta["suppressed"][0]["what"] == "wick_fill promotion blocker"


def test_run_weekly_review_sends_the_folded_html_once(monkeypatch):
    """The send boundary (replaces the 2026-08-30 source pin with behaviour): ONE send, HTML
    mode, head converted through `md_to_html`, fold wrapped as the expandable quote, and the
    report meta persisted with the review. MUTATION: `parse_mode="HTML"` → `"Markdown"` in
    `run_weekly_review` — the kwarg assertion reddened. RED, restored."""
    import agents.market_intelligence.collector as collector
    monkeypatch.setattr(collector, "et_today", lambda: TODAY)
    monkeypatch.setattr(sr, "_gather_and_aggregate", AsyncMock(return_value={"regime": {"current": "Up"}}))
    monkeypatch.setattr(sr, "get_latest_system_review", AsyncMock(return_value=None))
    monkeypatch.setattr(sr, "_synthesize", AsyncMock(return_value="⚠️ *Anomalies to verify*\n• one"))
    monkeypatch.setattr(sr, "_assemble_report", AsyncMock(return_value=(
        "*head* & more", "fold `x`", {"needs_you": 0, "needs_me": 0, "suppressed": []})))
    inserted, sent = [], []
    monkeypatch.setattr(sr, "insert_system_review", AsyncMock(side_effect=lambda r: inserted.append(r)))
    monkeypatch.setattr(sr, "send_telegram_message",
                        AsyncMock(side_effect=lambda text, **kw: sent.append((text, kw)) or True))
    review = asyncio.run(sr.run_weekly_review(window_days=7))
    assert len(sent) == 1
    text, kw = sent[0]
    assert kw == {"parse_mode": "HTML"}
    assert text == "<b>head</b> &amp; more\n<blockquote expandable>fold x</blockquote>"
    assert inserted[0]["metrics"]["report"]["suppressed"] == []
    assert review["suggestions"] == ["one"]
