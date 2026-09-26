"""`scripts/probes/_505_parent_pass_dry_run.py` — sign-off tooling defects found on
adversarial review of #505 (commit b0bd97c9), fixed here.

THE DEFECTS (the engine itself, `theme_engine._run_parent_pass`, was verified correct
and dark — these are ALL in the probe / SSoT, never in production code):

1. `load_board` hardcoded `"description": ""` for every theme, with a comment claiming
   `--adjudicate` refetches it. It never did — every `--adjudicate` run sent the real
   Haiku adjudicator a BLANK thesis for both sides of every pair. Fixed by reading the
   real `mi_themes.description` in the SAME query as the rest of the board row (no
   separate fetch, no risk of a second query racing a `theme_date` rollover).
2. The board-summary line reported the FULL 37-item queue's `shadow_promoted` count
   next to the words "in tonight's queue" (which is the 6-item capped slice) — a
   population mismatch. `shadow_promoted_split` reports all three counts (board /
   whole queue / tonight's slice) explicitly so no number is unlabeled.

Both are tested here with zero DB/SSH access — `psql()` is monkeypatched per query
string, `subprocess.run` is never invoked, and Arm B's own pairing
(`propose_merge_pairs`) is neutralized so this file tests only the parent-pass /
reporting logic it claims to, not Arm B's independent Stage-A heuristics.
"""
from __future__ import annotations

import asyncio
import os
import sys
import types

# The probe module sets APOLLO_CALL_ORIGIN=probe at IMPORT TIME (`os.environ.setdefault`, its
# own CLI-context marker — scripts/probes/_505_parent_pass_dry_run.py's top-level statement,
# unrelated to this task's fixes). That's a raw, un-monkeypatched process-wide mutation: without
# restoring it here, importing the probe module for testing would leak "probe" into
# `os.environ` for the REST OF THE PYTEST SESSION and silently corrupt any later test file that
# branches on it — `agents/market_intelligence/llm_health.py` reads this exact var to detect
# probe-origin calls and changes alert/audit behaviour accordingly (found via a full-suite run:
# this import alone flipped 12 unrelated `test_api_failure_guard.py` / `test_679_perplexity_
# failure_is_not_a_finding.py` assertions before this restore was added). Capture-and-restore,
# not a blind pop, so a real pre-existing value (unlikely, but not this test's business) survives
# untouched.
_had_call_origin = "APOLLO_CALL_ORIGIN" in os.environ
_prior_call_origin = os.environ.get("APOLLO_CALL_ORIGIN")

from scripts.probes import _505_parent_pass_dry_run as probe  # noqa: E402

if _had_call_origin:
    os.environ["APOLLO_CALL_ORIGIN"] = _prior_call_origin
else:
    os.environ.pop("APOLLO_CALL_ORIGIN", None)


# ── shadow_promoted_split — pure, no mocking ────────────────────────────────────────


def _theme(name, source="live", tickers=("A", "B")):
    return {"name": name, "source": source, "tickers": list(tickers)}


def _cand(child, child_source="live"):
    return {"child": child, "child_source": child_source}


def test_shadow_promoted_split_reports_board_queue_and_tonight_separately():
    # THE #505 SIGN-OFF BUG, reproduced: 2 shadow_promoted themes on the board, both
    # eligible and both in the 37-item queue, NEITHER in tonight's smaller capped slice
    # (mirrors the real 2026-09-25 dry run: 8 on the board, 5 in the queue, 0 tonight).
    live = [_theme("A", "shadow_promoted"), _theme("B", "shadow_promoted"), _theme("C", "live")]
    queue = [_cand("A", "shadow_promoted"), _cand("B", "shadow_promoted"), _cand("C", "live")]
    tonight = [_cand("C", "live")]  # neither shadow_promoted candidate made the cap tonight

    split = probe.shadow_promoted_split(live, queue, tonight)

    assert split == {"board": 2, "queue": 2, "tonight": 0}


def test_shadow_promoted_split_counts_tonight_when_present():
    live = [_theme("A", "shadow_promoted")]
    queue = [_cand("A", "shadow_promoted")]
    tonight = [_cand("A", "shadow_promoted")]  # this time it DOES make the cap

    split = probe.shadow_promoted_split(live, queue, tonight)

    assert split == {"board": 1, "queue": 1, "tonight": 1}


def test_main_reports_tonight_count_not_queue_count(monkeypatch, capsys):
    # MUTATION TARGET: reverting to counting over `queue` next to the words "tonight's
    # N capped ask(s)" — the exact #505 sign-off defect (a 2-of-2 queue count printed
    # as if it were the 1-item capped slice below). Drives `main()` end-to-end with
    # every DB call monkeypatched — no ssh, no LLM — and Arm B neutralized so only the
    # parent-pass logic under test decides what's eligible.
    board_rows = [
        # name, stage, parent, source, tickers, score, description
        ["Child1", "Nascent", "", "shadow_promoted", "AAA,BBB", "50", "d1"],
        ["Child2", "Nascent", "", "shadow_promoted", "CCC,DDD", "40", "d2"],
        ["Parent1", "Mainstream", "", "live", "AAA,BBB,CCC,DDD,EEE,FFF", "90", "d3"],
    ]
    eco_rows = [["Child1", "E-TEST"], ["Child2", "E-TEST"], ["Parent1", "E-TEST"]]

    def _fake_psql(query):
        if query == probe.Q_DATE:
            return [["2026-09-25"]]
        if query == probe.Q_BOARD:
            return board_rows
        if query == probe.Q_ECO:
            return eco_rows
        if query == probe.Q_COOL:
            return []
        if query == probe.Q_SECT:
            return []
        raise AssertionError(f"unexpected query: {query!r}")

    monkeypatch.setattr(probe, "psql", _fake_psql)
    # Neutralize Arm B entirely — this test is about the parent-pass reporting bug,
    # not about whether Arm B's independent Stage-A pairing would also claim this pair.
    monkeypatch.setattr(probe, "propose_merge_pairs", lambda *a, **k: [])
    # Force the nightly cap down to 1 so at most one of the two eligible shadow_promoted
    # children can ever land in "tonight's" slice, regardless of tie-break ordering.
    monkeypatch.setattr(probe.te, "PARENT_PASS_CAP_PER_NIGHT", 1)
    monkeypatch.setattr(sys, "argv", ["_505_parent_pass_dry_run.py"])

    rc = probe.main()
    assert rc == 0

    out = capsys.readouterr().out
    line = next(l for l in out.splitlines() if l.startswith("shadow_promoted themes on the board"))
    # Both candidates are shadow_promoted and both are eligible (same-ecosystem broader
    # parent, no cooldown, no Arm-B claim) -> both are in the whole queue; the cap of 1
    # means AT MOST one is in tonight's slice. The bug reprints the QUEUE count (2) next
    # to "tonight's" — this assertion is red on that behaviour.
    assert "board: 2 " in line
    assert "whole backfill queue" in line
    assert "of tonight's 1 capped ask(s))" in line
    assert "2 of tonight's" not in line


# ── load_board / description fetch ──────────────────────────────────────────────────


def test_load_board_carries_the_real_description_not_a_blank_placeholder(monkeypatch):
    # THE #505 SIGN-OFF BUG: a prior version hardcoded "" here unconditionally.
    def _fake_psql(query):
        if query == probe.Q_DATE:
            return [["2026-09-25"]]
        assert query == probe.Q_BOARD
        return [["ThemeA", "Nascent", "", "live", "AAA,BBB", "50",
                  "Real thesis text for ThemeA, not blank"]]

    monkeypatch.setattr(probe, "psql", _fake_psql)

    _day, board = probe.load_board()

    assert len(board) == 1
    assert board[0]["description"] == "Real thesis text for ThemeA, not blank"
    assert board[0]["description"] != ""


def test_adjudicate_sends_the_real_description_to_the_adjudicator(monkeypatch):
    # End-to-end proof that a real (non-blank) description reaches the adjudicator:
    # `by_name` is built straight from `load_board`'s output in `main()`, so once
    # `load_board` carries real descriptions, `_adjudicate` needs no separate fetch —
    # it already has them. Pin that wiring here so a future refactor can't silently
    # reintroduce a second, blank-defaulting theme dict for the adjudication path.
    captured: dict = {}

    async def _fake_adjudicate_merge_pair(theme_a, theme_b, *, client, sectors_by_ticker,
                                          log_spend=False):
        captured["theme_a_desc"] = theme_a.get("description")
        captured["theme_b_desc"] = theme_b.get("description")
        return {"verdict": "DISTINCT", "reason": "ok"}

    fake_module = types.SimpleNamespace(adjudicate_merge_pair=_fake_adjudicate_merge_pair)
    monkeypatch.setitem(sys.modules, "agents.market_intelligence.theme_merge_arm", fake_module)
    monkeypatch.setattr("shared.llm_client.make_async_anthropic", lambda: object())

    by_name = {
        "Parent": {"name": "Parent", "description": "Parent thesis", "tickers": ["A"]},
        "Child": {"name": "Child", "description": "Child thesis", "tickers": ["B"]},
    }
    queue = [{"child": "Child", "parent": "Parent"}]

    asyncio.run(probe._adjudicate(queue, by_name, sectors={}, out_path=None))

    assert captured["theme_a_desc"] == "Parent thesis"
    assert captured["theme_b_desc"] == "Child thesis"
