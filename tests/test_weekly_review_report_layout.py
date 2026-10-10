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
        # `is_live` / `ready_to_flip` are the fields the head decides on (#662, 2026-09-20) — it
        # used to string-match the `verdict` prose, so a rewording silently killed the "needs you"
        # line. They mirror what `_aggregate_crypto_readiness` really returns; keep them in step.
        "crypto": {"verdict": "✅ live; gates clean", "shadow_mode": False, "universe_size": 331,
                   "is_live": True, "ready_to_flip": False,
                   "rs_history_days": 135, "macro_history_days": 135, "ingest_attempts_7d": 6},
        "judge_weekly": {"total": 0}, "loser_breakdown": {}, "mfe_capture": {},
        "missed_opportunities": {},
    }
    theme_rows = overrides.pop("theme_rows", [])
    spend_callers = overrides.pop("spend_callers", [])
    closed_pnl = overrides.pop("closed_pnl", [])
    metrics.update(overrides)
    monkeypatch.setattr(sr, "get_engine_vs_judge_theme_rows", AsyncMock(return_value=theme_rows))
    monkeypatch.setattr(sr, "get_judge_graded_alert_flags", AsyncMock(return_value=_flags(theme_rows)))
    monkeypatch.setattr("agents.market_intelligence.cost_board.compute_caller_spend_window",
                        AsyncMock(return_value=spend_callers))
    monkeypatch.setattr(sr, "get_closed_pnl_by_account_mode", AsyncMock(return_value=closed_pnl))
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
                   "crypto: live, gates clean", "spend: $25.65 of $150", "themes: 30d n=0",
                   "30d LLM $0 vs no live close"):
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


def test_crypto_ready_to_flip_reaches_the_head_even_if_the_verdict_is_reworded(monkeypatch):
    """⚠ Found by the 2026-09-20 simplify pass. The ACTION head used to decide by searching the
    RENDERED verdict for the literal words "ready to flip". That made a user-visible call to the
    operator depend on prose: an emoji swap, a rephrase, a translation, and the "needs you" line
    stops firing with nothing failing — the exact silent drop #662 was built to remove.

    So this test rewords the verdict to something no substring match would catch, and still
    demands the head raise it. RED against the old `if "ready to flip" in verdict`."""
    head, _fold, meta = _assemble(monkeypatch, crypto={
        "verdict": "🟢 all gates clear — CRYPTO_RS_ENABLED can go true whenever you like",
        "shadow_mode": True, "is_live": False, "ready_to_flip": True,
        "universe_size": 331, "rs_history_days": 135, "ingest_attempts_7d": 6,
    })
    assert meta["needs_you"] == 1, f"a ready-to-flip crypto call did not reach the head: {head!r}"
    assert "crypto RS" in head


def test_crypto_not_ready_is_not_raised_with_him(monkeypatch):
    """The other direction, so the test above cannot be satisfied by raising everything.
    [[never-re-ask-an-answered-question]] — a blocked gate is MY work, not his decision."""
    _head, _fold, meta = _assemble(monkeypatch, crypto={
        "verdict": "⏳ not ready: crypto_categories empty",
        "shadow_mode": True, "is_live": False, "ready_to_flip": False,
        "universe_size": 331, "rs_history_days": 135, "ingest_attempts_7d": 6,
    })
    assert meta["needs_you"] == 0, "a blocked crypto gate was put in front of him as a decision"


def test_ripe_reviews_are_my_work_not_his_and_their_list_leads_the_fold(monkeypatch):
    """2026-10-05: the digest put ripe data-gated reviews under 'Needs you (4)' while
    scripts/operator_asks.py — the SoT for what waits on him — files them as MY work ('GATED
    REVIEWS NOW READY: MY WORK IS DUE, NOT HIS ANSWER'). He read a week of my reviews as his asks."""
    ready = [{"review_id": "r1", "title": "Steady-state cost of theme assignment", "kind": "accrual",
              "earliest_review_date": (TODAY - timedelta(days=3)).isoformat(),
              "action_when_ready": "Report cost and pool as a pair."}]
    head, fold, meta = _assemble(monkeypatch, pending_reviews={"ready": ready, "pending_count": 54})
    assert "Needs you" not in head
    assert "*Needs me (1):*" in head and "1 data-gated review(s) ripe" in head
    assert fold.startswith("📅 *Reviews ready* (1)") and "Steady-state cost of theme assignment" in fold


# ── #486 — engine vs judge theme agreement (2026-10-10) ──────────────────────────────────────
# Telemetry only. Each test names the mutation that reddened it.

def _tr(ticker, d, engine, judge, name=None, stage=None):
    """One `db.get_engine_vs_judge_theme_rows` row."""
    return {"ticker": ticker, "alert_date": d, "engine_theme": engine, "judge_theme": judge,
            "theme_name_7d": name, "theme_stage_7d": stage}


def _flags(rows, *extra):
    """`db.get_judge_graded_alert_flags` rows for the same alerts as `rows` (every clean row is
    also judge-graded), plus any `extra` left-out alerts. Defaults a fixture to 'nothing left
    out', so the pre-existing tests are unaffected by the coverage clause."""
    return [{"ticker": r["ticker"], "alert_date": r["alert_date"], "judge_theme": r["judge_theme"]}
            for r in rows] + list(extra)


def _left_out(ticker, d, judge):
    """A judge-graded alert the clean-read filter did NOT return (disagreeing / absent shadow)."""
    return {"ticker": ticker, "alert_date": d, "judge_theme": judge}


def _patch_theme_reads(monkeypatch, rows, graded=None):
    """Both #486 reads, the clean rows and the judge-graded denominator; returns the two mocks."""
    clean, denom = AsyncMock(return_value=rows), AsyncMock(
        return_value=_flags(rows) if graded is None else graded)
    monkeypatch.setattr(sr, "get_engine_vs_judge_theme_rows", clean)
    monkeypatch.setattr(sr, "get_judge_graded_alert_flags", denom)
    return clean, denom


D = TODAY - timedelta(days=2)      # inside the 7-day window


def test_theme_agreement_counts_the_2x2_and_buckets_every_judge_only_row():
    """The 2x2 and the mismatch cohorts. Judge-only rows are bucketed from the shadow's BOUNDED
    read, and the buckets must sum to the judge-only count (exhaustive by construction).
    MUTATION: `stage == "Fading"` branch deleted from `_theme_miss_reason` — Fading rows fell
    into `artifact` and the Fading count went to 0. RED, restored."""
    rows = [
        _tr("AAA", D, True, True, "Cloud", "Mainstream"),                      # both
        _tr("BBB", D, True, False, "Cloud", "Mainstream"),                     # engine only
        _tr("CCC", D, False, True),                                            # judge only: no row
        _tr("DDD", D, False, True, "Quantum", "Fading"),                       # judge only: Fading
        _tr("EEE", D, False, True, "Space", "Nascent"),                        # judge only: Nascent
        _tr("FFF", D, False, True, "Cloud", "Mainstream"),                     # judge only: artifact
        _tr("GGG", D, False, True, "Odd", "Weird"),                            # judge only: other
        _tr("HHH", D, False, False),                                           # neither
        _tr("III", D, False, False, "Cloud", "Mainstream"),                    # neither
    ]
    a = sr._aggregate_theme_agreement(rows)
    assert (a["n"], a["both"], a["engine_only"], a["judge_only"], a["neither"]) == (9, 1, 1, 5, 2)
    assert a["reasons"] == {"no_theme_row": 1, "excluded_fading": 1, "excluded_nascent": 1,
                            "artifact": 1, "other_stage": 1}
    assert sum(a["reasons"].values()) == a["judge_only"]
    assert a["agree_pct"] == round(100 * 3 / 9)


def test_theme_agreement_queue_leads_with_coverage_gaps_then_newest():
    """The engine-improvement queue: genuine coverage gaps (no theme row) before deliberate
    exclusions, newest first inside a tier. MUTATION: the second (rank) sort deleted — the queue
    came out purely date-ordered with a Fading row ahead of an older no-row gap. RED, restored."""
    rows = [
        _tr("NEWFAD", D, False, True, "Q", "Fading"),
        _tr("OLDGAP", D - timedelta(days=3), False, True),
        _tr("NEWGAP", D - timedelta(days=1), False, True),
    ]
    q = sr._aggregate_theme_agreement(rows)["queue"]
    assert [x["ticker"] for x in q] == ["NEWGAP", "OLDGAP", "NEWFAD"]


def test_theme_agreement_queue_is_capped_with_a_plus_n_more():
    """MUTATION: slice `[:_THEME_QUEUE_CAP]` removed — all 11 names printed and the "+3 more"
    line vanished. RED, restored."""
    rows = [_tr(f"T{i:02d}", D - timedelta(days=i % 3), False, True) for i in range(11)]
    text = sr._format_theme_agreement(sr._aggregate_theme_agreement(rows), None, today=TODAY)
    assert text.count("\n• ") == sr._THEME_QUEUE_CAP
    assert "+3 more" in text


def test_theme_agreement_a_small_week_also_shows_the_trailing_30_days_with_both_ns(monkeypatch):
    """A weekly n of 3 is a handful of names, so the trailing 30 days prints beside it and BOTH
    n are stated. The boundary day (window_start itself) belongs to the week; the day before it
    does not. MUTATION: `weekly["n"] < _THEME_AGREEMENT_MIN_N` flipped to `False` — the trailing
    line vanished. RED, restored."""
    ws = TODAY - timedelta(days=7)
    rows = [_tr("A", D, True, True, "Cloud", "Mainstream"), _tr("B", ws, False, False),
            _tr("C", D, False, True),
            _tr("OLD1", ws - timedelta(days=1), False, False), _tr("OLD2", ws - timedelta(days=9), False, True)]
    fetch, denom = _patch_theme_reads(monkeypatch, rows)
    text, phrase = asyncio.run(sr._theme_agreement_section(ws, TODAY))
    assert "This week (n=3)" in text and "Last 30 days to Sep 20 (n=5)" in text
    assert phrase == "themes: 30d n=5, 60% engine-judge agree"
    # one fetch spanning the trailing window, split in Python
    assert fetch.await_args.args == (TODAY - timedelta(days=29), TODAY)
    assert denom.await_args.args == (TODAY - timedelta(days=29), TODAY)     # same window, both reads
    assert "OLD2" in text                      # the 30-day cohort feeds the queue, not the week alone
    assert "in the last 30 days:" in text      # the trailing basis keeps its article


def test_theme_agreement_a_full_week_stands_alone(monkeypatch):
    """The other direction, so the trailing line is not printed unconditionally."""
    rows = [_tr(f"T{i}", D, False, False) for i in range(sr._THEME_AGREEMENT_MIN_N)]
    _patch_theme_reads(monkeypatch, rows)
    text, phrase = asyncio.run(sr._theme_agreement_section(TODAY - timedelta(days=7), TODAY))
    assert "Last 30 days" not in text and phrase == "themes: 7d n=10, 100% engine-judge agree"


def test_theme_agreement_a_full_week_with_a_judge_only_miss_reads_in_this_week(monkeypatch):
    """A weekly n of 10 skips the 30-day block, so the miss line's basis is 'this week'. It used to
    print 'in the this week:' (basis_label carried no article but the f-string added one).
    MUTATION: the f-string's `in {basis_label}` put back to `in the {basis_label}` - the 'in the this
    week' form returned and this reddened. RED, restored."""
    rows = [_tr(f"T{i}", D, False, False) for i in range(sr._THEME_AGREEMENT_MIN_N - 1)]
    rows.append(_tr("MISS", D, False, True))                       # the one judge-only row
    _patch_theme_reads(monkeypatch, rows)
    text, _phrase = asyncio.run(sr._theme_agreement_section(TODAY - timedelta(days=7), TODAY))
    assert "Last 30 days" not in text                              # the weekly n is 10: stands alone
    assert "did not — 1 in this week: no theme row at all 1" in text
    assert "the this week" not in text


def test_theme_agreement_failed_read_says_unavailable_and_the_review_still_assembles(monkeypatch):
    """Fail-open: a dead read prints a short `unavailable:` line (not silence, not a crash), the
    message cannot carry markup that breaks the send, and the REST of the review still builds.
    MUTATION: `except` in `_theme_agreement_section` narrowed to `ValueError` — the RuntimeError
    escaped and the section vanished from the fold. RED, restored."""
    async def boom(*_a, **_k):
        raise RuntimeError("relation `mi_theme_axis_shadow` *gone* " + "x" * 200)
    text, phrase = asyncio.run(_run_section_with(monkeypatch, boom))
    assert "unavailable: RuntimeError: relation mi_theme_axis_shadow gone" in text
    assert "*gone*" not in text and "`" not in text and len(text) < 220
    assert phrase == "themes: unavailable"
    head, fold, _meta_ = _assemble(monkeypatch)
    assert "unavailable" not in fold                       # the quiet fixture is NOT unavailable
    monkeypatch.setattr(sr, "get_engine_vs_judge_theme_rows", boom)
    head, fold, _meta_ = asyncio.run(sr._assemble_report(
        {"regime": {"current": "Up"}}, "narrative", TODAY - timedelta(days=7), TODAY))
    assert "Theme read, engine vs judge (#486):* unavailable:" in fold
    assert "themes: unavailable" in head and "Weekly review" in head


async def _run_section_with(monkeypatch, fetch):
    monkeypatch.setattr(sr, "get_engine_vs_judge_theme_rows", fetch)
    return await sr._theme_agreement_section(TODAY - timedelta(days=7), TODAY)


def test_theme_agreement_is_fold_only_and_never_asks_anything_of_him(monkeypatch):
    """ZERO AUTHORITY: even with every alert a judge-only miss, nothing reaches the head's
    action lists. MUTATION: a `needs_me.append(...)` added beside the fold append — needs_me
    went to 1. RED, restored."""
    rows = [_tr(f"T{i}", D, False, True) for i in range(6)]
    head, fold, meta = _assemble(monkeypatch, theme_rows=rows)
    assert meta["needs_you"] == 0 and meta["needs_me"] == 0
    assert "Theme read" not in head and "Theme read, engine vs judge (#486)" in fold
    assert "themes: 30d n=6, 0% engine-judge agree" in head


def test_the_engine_vs_judge_query_filters_to_clean_deduplicated_judge_graded_rows():
    """The population is the whole point of #486 (the 08-29 instrument defect): only rows where
    the bounded and unbounded theme reads agree, only alerts the judge adjudicated, and the
    alerts side de-duplicated (mi_ep_alerts has no unique (ticker, alert_date)).
    MUTATION: each of the three clauses deleted in turn — this test reddened on each."""
    import agents.market_intelligence.db as dbmod
    from tests.conftest import make_mock_pool
    from unittest.mock import patch
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[{"ticker": "A"}])
    with patch.object(dbmod, "get_pool", new=AsyncMock(return_value=pool)):
        out = asyncio.run(dbmod.get_engine_vs_judge_theme_rows(date(2026, 9, 1), date(2026, 9, 20)))
    sql = " ".join(conn.fetch.await_args.args[0].split())
    assert out == [{"ticker": "A"}]
    assert "s.bounded_matches_unbounded IS TRUE" in sql
    assert "fire_axes IS NOT NULL" in sql
    assert "DISTINCT ON (ticker, alert_date)" in sql
    # which duplicate survives is part of the contract: the NEWEST row (the scan's last word)
    assert "ORDER BY ticker, alert_date, id DESC" in sql
    assert "in_active_theme IS TRUE" in sql and "'theme' = ANY(a.fire_axes)" in sql
    assert conn.fetch.await_args.args[1:] == (date(2026, 9, 1), date(2026, 9, 20))


def test_the_judge_graded_denominator_query_has_no_shadow_filter_and_the_same_dedupe():
    """The coverage clause is `graded - clean`, so the denominator must be the SAME alerts side as
    the clean-row query (same DISTINCT ON, same newest-id survivor, same fire_axes IS NOT NULL)
    and must NOT join or filter on the shadow (that would make it the clean set again).
    MUTATION: each of the three alert-side clauses deleted in turn, and a shadow join added -
    this test reddened on each."""
    import agents.market_intelligence.db as dbmod
    from tests.conftest import make_mock_pool
    from unittest.mock import patch
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[{"ticker": "A", "alert_date": date(2026, 9, 2), "judge_theme": True}])
    with patch.object(dbmod, "get_pool", new=AsyncMock(return_value=pool)):
        out = asyncio.run(dbmod.get_judge_graded_alert_flags(date(2026, 9, 1), date(2026, 9, 20)))
    sql = " ".join(conn.fetch.await_args.args[0].split())
    assert out == [{"ticker": "A", "alert_date": date(2026, 9, 2), "judge_theme": True}]
    assert "FROM mi_ep_alerts" in sql and "fire_axes IS NOT NULL" in sql
    assert "DISTINCT ON (ticker, alert_date)" in sql and "ORDER BY ticker, alert_date, id DESC" in sql
    assert "COALESCE('theme' = ANY(fire_axes), FALSE) AS judge_theme" in sql
    assert "mi_theme_axis_shadow" not in sql and "bounded_matches_unbounded" not in sql
    assert conn.fetch.await_args.args[1:] == (date(2026, 9, 1), date(2026, 9, 20))


def test_theme_agreement_discloses_the_judge_graded_alerts_the_clean_read_filter_left_out():
    """The clean-read filter drops judge-graded alerts (a disagreeing or absent shadow read) and
    several of them are alerts the judge themed. The 2x2's n stays the CLEAN count, but the footer
    states how many alerts it covers out of how many judge-graded and how many of the left-out
    ones the judge themed. The query returns date-desc/ticker order, so left-out alerts are
    INTERLEAVED with clean ones - the difference is by (ticker, date) key, never by position.
    MUTATION: `excluded_judge` counted over every graded alert instead of the left-out ones (3
    instead of 2), and the key difference replaced by `graded[len(rows):]` (picked the wrong
    alerts out of the interleaved list) - both reddened. RED, restored."""
    rows = [_tr("AAA", D, True, True, "Cloud", "Mainstream"), _tr("BBB", D, False, False)]
    graded = [_left_out("CEG", D, True), *_flags(rows[:1]), _left_out("MSTR", D, False),
              *_flags(rows[1:]), _left_out("VST", D, True)]
    a = sr._aggregate_theme_agreement(rows, graded)
    assert a["n"] == 2                                   # the 2x2 is unchanged by the left-out rows
    assert (a["graded_n"], a["excluded"], a["excluded_judge"]) == (5, 3, 2)
    text = sr._format_theme_agreement(a, None, today=TODAY)
    assert ("Counts 2 of 5 judge-graded alerts in this week; 3 left out where the engine's 7-day and "
            "unbounded theme reads disagree or none was captured, 2 of them judge-themed.") in text
    # nothing left out -> says so, no stray "0 left out"
    clean = sr._aggregate_theme_agreement(rows, _flags(rows))
    assert "Counts all 2 judge-graded alerts in this week." in sr._format_theme_agreement(
        clean, None, today=TODAY)
    # no denominator supplied -> the old, count-free sentence, never a wrong count
    assert "Counts only alerts where the engine's 7-day and unbounded theme reads agree." in \
        sr._format_theme_agreement(sr._aggregate_theme_agreement(rows), None, today=TODAY)


def test_theme_agreement_footer_states_the_judge_definition_and_the_basis_window(monkeypatch):
    """The footer names what 'judge saw a theme' means ('theme' axis only; the live blind-spot
    classifier also counts 'narrative', so the difference is stated rather than left implicit) and
    the coverage clause follows the window the queue is read from (the trailing 30 days when the
    week is small). Left-out alerts are split by the same window cut as the clean rows.
    MUTATION: the coverage clause read off `weekly` instead of the trailing basis - '1 left out'
    appeared instead of '2'. RED, restored."""
    ws = TODAY - timedelta(days=7)
    rows = [_tr("A", D, True, True, "Cloud", "Mainstream")]
    old = ws - timedelta(days=5)
    graded = _flags(rows, _left_out("NEW", D, True), _left_out("OLDX", old, True))
    _patch_theme_reads(monkeypatch, rows, graded)
    text, _phrase = asyncio.run(sr._theme_agreement_section(ws, TODAY))
    assert "judge = it lit its 'theme' axis (the 'narrative' axis is not counted)" in text
    assert ("Counts 1 of 3 judge-graded alerts in the last 30 days; 2 left out where the engine's "
            "7-day and unbounded theme reads disagree or none was captured, 2 of them "
            "judge-themed.") in text


def test_theme_agreement_a_failed_denominator_read_says_unavailable(monkeypatch):
    """Fail-open covers the SECOND read too: the clean rows fetched fine but the judge-graded
    denominator died - the block prints `unavailable:` rather than a 2x2 with a wrong coverage
    line, and the review still assembles. MUTATION: the denominator call moved outside the
    section's try - the RuntimeError escaped. RED, restored."""
    async def boom(*_a, **_k):
        raise RuntimeError("denominator read died")
    monkeypatch.setattr(sr, "get_engine_vs_judge_theme_rows", AsyncMock(return_value=[]))
    monkeypatch.setattr(sr, "get_judge_graded_alert_flags", boom)
    text, phrase = asyncio.run(sr._theme_agreement_section(TODAY - timedelta(days=7), TODAY))
    assert "unavailable: RuntimeError: denominator read died" in text
    assert phrase == "themes: unavailable"


# ── #313 part 2 — LLM spend by caller vs realised P&L (2026-10-10) ────────────────────────────

def _caller(name, spend, calls):
    return {"caller": name, "spend": spend, "calls": calls}


def _book(mode, n, wins, pnl):
    return {"account_mode": mode, "n": n, "wins": wins, "total_pnl": pnl}


def test_spend_vs_pnl_aggregate_totals_the_judge_callers_and_puts_live_first():
    """Totals, the 'judge' name-match subtotal, zero-spend callers dropped, and the live book
    ahead of paper whatever order the query returned. MUTATION: the `"judge" in` filter deleted
    (every caller counted as judge) - judge_spend equalled total_spend. RED, restored."""
    agg = sr._aggregate_spend_vs_pnl(
        [_caller("ep_grade_judge", 40.0, 900), _caller("theme_discovery", 12.5, 30),
         _caller("judge_divergence", 7.5, 400), _caller("idle_lane", 0.0, 0)],
        [_book("paper", 12, 5, -45.0), _book("live", 9, 6, 1234.5)])
    assert agg["total_spend"] == 60.0 and agg["total_calls"] == 1330
    assert agg["judge_spend"] == 47.5
    assert [c["caller"] for c in agg["callers"]] == ["ep_grade_judge", "theme_discovery", "judge_divergence"]
    assert [b["account_mode"] for b in agg["books"]] == ["live", "paper"]


def test_spend_vs_pnl_block_reads_as_what_the_judge_cost_against_what_we_made():
    """The rendered block: spend, top callers, the judge subtotal and share, then P&L per book,
    never blended. MUTATION: the books loop collapsed to one summed line - the paper line (and its
    own count) vanished. RED, restored."""
    agg = sr._aggregate_spend_vs_pnl(
        [_caller("ep_grade_judge", 40.0, 900), _caller("theme_discovery", 20.0, 30)],
        [_book("live", 9, 6, 1234.5), _book("paper", 1, 0, -45.0)])
    text = sr._format_spend_vs_pnl(agg, window_start=date(2026, 9, 22), today=date(2026, 10, 21))
    assert "last 30 days, Sep 22 – Oct 21" in text
    assert "LLM spend: $60.00 across 930 calls" in text
    assert "• ep_grade_judge $40.00 (900 calls)" in text
    assert "Callers with 'judge' in the name: $40.00 (67% of spend)" in text
    assert "• live book (real money): $+1,234 over 9 closed trades (6 winners)" in text
    assert "• paper lane: $-45 over 1 closed trade (0 winners)" in text


def test_spend_vs_pnl_caps_the_caller_list_and_folds_the_tail():
    """MUTATION: slice `[:_SPEND_CALLER_CAP]` removed - all 9 callers listed, no tail line. RED,
    restored."""
    callers = [_caller(f"lane_{i}", 10.0 - i, 10) for i in range(9)]       # 10,9,8,7,6,5 | 4,3,2
    text = sr._format_spend_vs_pnl(sr._aggregate_spend_vs_pnl(callers, []),
                                   window_start=date(2026, 9, 22), today=date(2026, 10, 21))
    assert text.count("\n• lane_") == sr._SPEND_CALLER_CAP
    assert "• +3 other callers $9.00" in text


def test_spend_vs_pnl_the_live_book_always_prints_even_with_nothing_closed():
    """A month with no live close SAYS so instead of the line vanishing; a paper lane that closed
    nothing stays silent. MUTATION: the synthesized empty-live row removed - the live line was
    missing. RED, restored."""
    text = sr._format_spend_vs_pnl(sr._aggregate_spend_vs_pnl([_caller("a", 1.0, 1)], []),
                                   window_start=date(2026, 9, 22), today=date(2026, 10, 21))
    assert "• live book (real money): no trade closed" in text
    assert "paper lane" not in text


def test_spend_vs_pnl_section_reads_the_same_30_days_on_both_sides(monkeypatch):
    """The spend window and the P&L window are the same ET dates (today-29 .. today).
    MUTATION: the P&L window start changed to `today - _SPEND_PNL_DAYS` (31 days) - the args
    assertion reddened. RED, restored."""
    spend = AsyncMock(return_value=[_caller("ep_grade_judge", 40.0, 900)])
    pnl = AsyncMock(return_value=[_book("live", 3, 2, 150.0)])
    monkeypatch.setattr("agents.market_intelligence.cost_board.compute_caller_spend_window", spend)
    monkeypatch.setattr(sr, "get_closed_pnl_by_account_mode", pnl)
    text, phrase = asyncio.run(sr._spend_vs_pnl_section(TODAY))
    assert spend.await_args.args == (TODAY, 30)
    assert pnl.await_args.args == (TODAY - timedelta(days=29), TODAY)
    assert phrase == "30d LLM $40 vs live P&L $+150 on 3"
    assert "LLM spend: $40.00" in text and "$+150 over 3 closed trades" in text


@pytest.mark.parametrize("which", ["spend", "pnl"])
def test_spend_vs_pnl_failed_read_says_unavailable_and_the_review_still_assembles(monkeypatch, which):
    """Fail-open on EITHER side. MUTATION: `except` narrowed to `ValueError` - the RuntimeError
    escaped `_spend_vs_pnl_section`. RED, restored."""
    async def boom(*_a, **_k):
        raise RuntimeError("pool closed *abruptly*")
    ok = AsyncMock(return_value=[])
    monkeypatch.setattr("agents.market_intelligence.cost_board.compute_caller_spend_window",
                        boom if which == "spend" else ok)
    monkeypatch.setattr(sr, "get_closed_pnl_by_account_mode", boom if which == "pnl" else ok)
    text, phrase = asyncio.run(sr._spend_vs_pnl_section(TODAY))
    assert "unavailable: RuntimeError: pool closed abruptly" in text and "*abruptly*" not in text
    assert phrase == "spend vs P&L: unavailable"
    head, fold, _m = _assemble_with_current_patches(monkeypatch)
    assert "(#313):* unavailable:" in fold and "spend vs P&L: unavailable" in head


def _assemble_with_current_patches(monkeypatch):
    """Run the whole assembly WITHOUT `_assemble`'s defaults overwriting the failing patches the
    caller just installed (the other sections are quiet-week stubs, as in `_assemble`)."""
    _patch_theme_reads(monkeypatch, [])
    monkeypatch.setattr(sr, "_setup_performance_review", AsyncMock(return_value=("", [])))
    monkeypatch.setattr(sr, "_spend_envelope", AsyncMock(return_value=("💵 *Cost envelope (MTD)*", 1.0, 150.0, False)))
    monkeypatch.setattr(sr, "_judge_divergence_section", AsyncMock(return_value=""))
    verdict = ksb.BandVerdict(band="HOLD", action="No change", reasons=["within bands"], n_trades=5)
    monkeypatch.setattr(ksb, "assess_bands", AsyncMock(return_value=(_inputs([-1.0] * 5, _meta(5)), verdict, None)))
    monkeypatch.setattr(ksb, "assemble_band_inputs", AsyncMock(return_value=_inputs([-1.0] * 5, _meta(5))))
    monkeypatch.setattr(rr, "run_replay_regression", AsyncMock(return_value={"lines": []}))
    return asyncio.run(sr._assemble_report({"regime": {"current": "Up"}}, "narrative",
                                           TODAY - timedelta(days=7), TODAY))


def test_spend_vs_pnl_is_fold_only_and_never_a_budget_or_an_ask(monkeypatch):
    """ZERO AUTHORITY: a spend far over any budget and a deep loss still raise nothing in the head's
    action lists (the over-budget ask belongs to the MTD envelope alone). MUTATION: a
    `needs_you.append(...)` added beside the fold append - needs_you went to 1. RED, restored."""
    head, fold, meta = _assemble(
        monkeypatch, spend_callers=[_caller("ep_grade_judge", 9999.0, 10)],
        closed_pnl=[_book("live", 4, 0, -5000.0)])
    assert meta["needs_you"] == 0 and meta["needs_me"] == 0
    assert "LLM spend vs realised P&L (#313)" in fold and "LLM spend vs realised" not in head
    assert "30d LLM $9,999 vs live P&L $-5,000 on 4" in head


def test_the_closed_pnl_query_windows_on_the_et_close_date_and_pins_no_book():
    """The query counts what CLOSED in the window, in account accounting. MUTATION: each clause
    changed in turn (the ET cast, `status = 'closed'`, an added `pnl_attribution IS NULL`, a
    hard-coded `account_mode = 'live'`) - this reddened on each."""
    import agents.market_intelligence.db as dbmod
    from tests.conftest import make_mock_pool
    from unittest.mock import patch
    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[{"account_mode": "live", "n": 1, "wins": 1, "total_pnl": 5.0}])
    with patch.object(dbmod, "get_pool", new=AsyncMock(return_value=pool)):
        out = asyncio.run(dbmod.get_closed_pnl_by_account_mode(date(2026, 9, 22), date(2026, 10, 21)))
    sql = " ".join(conn.fetch.await_args.args[0].split())
    assert out == [{"account_mode": "live", "n": 1, "wins": 1, "total_pnl": 5.0}]
    assert "status = 'closed'" in sql
    assert "(closed_at AT TIME ZONE 'America/New_York')::date BETWEEN $1::date AND $2::date" in sql
    assert "GROUP BY account_mode" in sql
    assert "pnl_attribution" not in sql and "account_mode = '" not in sql
    assert conn.fetch.await_args.args[1:] == (date(2026, 9, 22), date(2026, 10, 21))
