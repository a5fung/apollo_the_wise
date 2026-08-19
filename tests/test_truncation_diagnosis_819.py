"""The truncation alert used to say ONE thing on every fire: "raise the ceiling in
shared/output_ceilings.py" (spend_tracker.py's live alarm + cost_board.py's nightly
digest). That advice was wrong for BOTH real cases it fired on the week of 2026-08-19:

  1. theme_discovery (2026-08-18): already raised 4000->8000 on 08-07 and pegged
     again. Seven clean days at 5.6k-6.7k peak, then one truncation on a
     double-volume day. The real fix was cutting the batch 37->22, not raising —
     and shared/output_ceilings.py already says so: theme_discovery is on the
     do-not-raise list, because a straight raise re-pegs within days.

  2. theme_validation (2026-08-19): mean output 31 tokens against a 1000 cap,
     all-time max 580, then one call hit the 1000 cap (~30x normal). Enormous
     headroom — an input anomaly (an oversized theme), not a ceiling problem.

`diagnose_truncation()` (shared/output_ceilings.py) replaces the blanket
instruction with a diagnosis read from the caller's OWN measured history:
DO-NOT-RAISE (sourced from output_ceilings.py, never duplicated — the set covers
both the four theme-engine callers AND the three theme_advisor_* callers, which
carry the identical "DO NOT raise again for at-cap pressure" verdict on _ADVISOR)
/ NO HEADROOM / AMPLE HEADROOM ONE OUTLIER. These tests pin all three outcomes
with the real numbers above, prove the do-not-raise judgment is sourced (not
copied) into both alert call sites — including the NEAR-CEILING footer, which
carries the identical wrong-advice bug — and prove neither message can put a
caller name or a do-not-raise path outside a Telegram code fence (#477 parity:
a bare underscore there breaks Markdown V1 italics).
"""
import asyncio
import pathlib
from unittest.mock import AsyncMock

from shared import output_ceilings as oc

REPO = pathlib.Path(__file__).resolve().parents[1]
TRACKER_SRC = (REPO / "agents/market_intelligence/spend_tracker.py").read_text(encoding="utf-8")
BOARD_SRC = (REPO / "agents/market_intelligence/cost_board.py").read_text(encoding="utf-8")


def _outside_fences(text: str) -> str:
    """Telegram Markdown V1 treats a ``` fence as opaque; everything else is
    subject to *bold*/_italic_ parsing. Splitting on "```" and keeping the
    even-indexed segments recovers exactly the text NOT protected by a fence."""
    parts = text.split("```")
    return "".join(p for i, p in enumerate(parts) if i % 2 == 0)


_MAX_FENCED_LINE = 80  # a Telegram code block does NOT wrap on a phone — a long
# line just scrolls off-screen. 80 comfortably covers every pre-existing line in
# this file (headers, the stats table) while still catching a runaway diagnosis
# — the first version of diagnose_truncation produced a ~250-char single line.


def _assert_fenced_lines_are_short(text: str) -> None:
    parts = text.split("```")
    fenced = [p for i, p in enumerate(parts) if i % 2 == 1]
    for block in fenced:
        for line in block.split("\n"):
            assert len(line) <= _MAX_FENCED_LINE, (
                f"fenced line is {len(line)} chars (max {_MAX_FENCED_LINE}) and will "
                f"scroll off a phone instead of wrapping: {line!r}")


def _assert_fenced(text: str, *needles: str) -> None:
    """Every `needle` (a caller name, an underscored path) must appear ONLY
    inside a ``` fence — never in the free-text outside it, where Telegram
    Markdown V1 would read its underscores as italic markers (#477 parity).
    Scoped to the specific strings THIS change introduces, not a blanket
    no-underscore rule — the header text ("cut off by max_tokens") predates
    this change and is out of scope here."""
    outside = _outside_fences(text)
    for needle in needles:
        assert needle not in outside, (
            f"{needle!r} sits outside the code fence — Telegram Markdown V1 will "
            "read its underscore(s) as italic markers and mangle the message")


# ── 1. the do-not-raise list is sourced from output_ceilings.py, never duplicated ──────────

def test_do_not_raise_list_covers_theme_engine_and_theme_advisor():
    assert oc.DO_NOT_RAISE_FOR_AT_CAP_PRESSURE == {
        "theme_assignment", "theme_discovery", "theme_split",
        "narrative_theme_discovery",
        "theme_advisor_discovery", "theme_advisor_split", "theme_advisor_assignment",
    }
    for caller in oc.DO_NOT_RAISE_FOR_AT_CAP_PRESSURE:
        assert caller in oc.CEILINGS, (
            f"{caller} is on the do-not-raise list but not registered — an "
            "unregistered do-not-raise name protects nothing")


def test_neither_alert_call_site_hardcodes_its_own_copy():
    """The whole point of sourcing this from output_ceilings.py: a second copy
    would drift. Neither spend_tracker.py nor cost_board.py may hardcode its own
    version of the do-not-raise set — they must call diagnose_truncation()."""
    for src, label in ((TRACKER_SRC, "spend_tracker.py"), (BOARD_SRC, "cost_board.py")):
        for caller in oc.DO_NOT_RAISE_FOR_AT_CAP_PRESSURE:
            assert f'"{caller}"' not in src, (
                f"{label} hardcodes do-not-raise caller {caller!r} — read it from "
                "shared/output_ceilings.py via diagnose_truncation() instead")
        assert "diagnose_truncation" in src, (
            f"{label} no longer calls the shared diagnosis function")


# ── 2. diagnose_truncation — the three situations, with the real numbers ───────────────────

def test_theme_discovery_08_18_diagnoses_do_not_raise():
    """Real case #1. Correct advice: do NOT raise (it's on the list); the real fix
    was cutting the batch, which the diagnosis must point away from raising to."""
    diag = oc.diagnose_truncation(
        "theme_discovery", cap=8000, this_call_tokens=8000,
        mean_completed=6100.0, typical_max_completed=6700,
    )
    assert "do-not-raise" in diag
    assert "6700" in diag and "8000" in diag  # the numbers that justify it
    assert "raise the ceiling" not in diag.lower()
    assert "don't raise" in diag
    assert len(diag) <= 70, (
        "diagnosis text renders in a Telegram code block, which does NOT wrap on "
        f"a phone — keep it short (got {len(diag)} chars): {diag!r}")


def test_theme_validation_08_19_diagnoses_ample_headroom_one_outlier():
    """Real case #2. Correct advice: an input anomaly, not a ceiling problem —
    must NOT land on the do-not-raise branch (theme_validation isn't listed) and
    must NOT read as "no headroom"."""
    diag = oc.diagnose_truncation(
        "theme_validation", cap=1000, this_call_tokens=1000,
        mean_completed=31.0, typical_max_completed=580,
    )
    assert "AMPLE HEADROOM" in diag
    assert "31" in diag and "580" in diag and "1000" in diag
    assert "32x" in diag  # this call (1000) is ~32x the 31-token mean
    assert "do-not-raise" not in diag
    assert "NO HEADROOM" not in diag
    assert len(diag) <= 70, f"got {len(diag)} chars: {diag!r}"


def test_theme_advisor_discovery_is_also_diagnosed_do_not_raise():
    """The _ADVISOR ceiling's own evidence ("DO NOT raise again for at-cap
    pressure — freeform-prose caller that fills ANY cap") applies to all three
    theme_advisor_* keys, not just the four theme-engine callers."""
    diag = oc.diagnose_truncation(
        "theme_advisor_discovery", cap=1500, this_call_tokens=1500,
        mean_completed=590.0, typical_max_completed=1500,
    )
    assert "do-not-raise" in diag
    assert "don't raise" in diag


def test_a_non_listed_caller_with_no_headroom_says_cap_may_be_the_constraint():
    """Situation 3: a registered, non-listed caller whose clean-call peak already
    sits at the near-ceiling threshold. This is the one case where raising might
    actually be right."""
    cap = oc.max_tokens_for("orchestrator")
    assert "orchestrator" not in oc.DO_NOT_RAISE_FOR_AT_CAP_PRESSURE
    diag = oc.diagnose_truncation(
        "orchestrator", cap=cap, this_call_tokens=cap,
        mean_completed=cap * 0.5, typical_max_completed=int(cap * 0.95),
    )
    assert "NO HEADROOM" in diag
    assert "constraint" in diag
    assert "do-not-raise" not in diag
    assert "bound input" not in diag
    assert len(diag) <= 70, f"got {len(diag)} chars: {diag!r}"


def test_no_completed_history_says_so_and_does_not_guess():
    diag = oc.diagnose_truncation(
        "ep_catalyst_grade", cap=1500, this_call_tokens=1500,
        mean_completed=None, typical_max_completed=None,
    )
    assert "no completed-call history" in diag
    assert "1500" in diag
    assert "NO HEADROOM" not in diag and "AMPLE HEADROOM" not in diag


# ── 3. spend_tracker's LIVE alert — end to end, real numbers, real caller names ────────────

class _FakeHistConn:
    def __init__(self, mean, mx):
        self._mean, self._mx = mean, mx

    async def fetchrow(self, sql, caller):
        assert "avg(output_tokens)" in sql and "caller = $1" in sql
        if self._mean is None:
            return {"mean_completed": None, "max_completed": None}
        return {"mean_completed": self._mean, "max_completed": self._mx}


class _FakeHistPool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        conn = self._conn

        class _Ctx:
            async def __aenter__(self):
                return conn

            async def __aexit__(self, *a):
                return False
        return _Ctx()


def _wire_live_alarm(monkeypatch, mean, mx):
    from agents.market_intelligence import spend_tracker as st
    conn = _FakeHistConn(mean, mx)

    async def _fake_get_pool():
        return _FakeHistPool(conn)
    monkeypatch.setattr(st, "get_pool", _fake_get_pool)

    audit = AsyncMock()
    tg = AsyncMock(return_value=True)
    import agents.market_intelligence.db as db_mod
    monkeypatch.setattr(db_mod, "log_audit_event", audit)
    import agents.market_intelligence.briefing as briefing_mod
    monkeypatch.setattr(briefing_mod, "send_telegram_message", tg)
    monkeypatch.setattr(st, "_TRUNCATION_TELEGRAMMED", {})
    return st, audit, tg


def test_live_alert_names_caller_model_cap_and_do_not_raise(monkeypatch):
    """theme_discovery truncates live: the alert must still name caller/model/cap
    (it is a real signal) AND must not tell the operator to raise a ceiling the
    codebase forbids raising — and every underscored token (caller name,
    shared/output_ceilings.py) must sit inside the code fence (#477 parity)."""
    st, audit, tg = _wire_live_alarm(monkeypatch, 6100.0, 6700)

    asyncio.run(st._maybe_alert_truncation(
        caller="theme_discovery", model="claude-sonnet-5", output_tokens=8000))

    tg.assert_awaited_once()
    text = tg.await_args.args[0]
    assert "theme_discovery" in text            # caller
    assert "claude-sonnet-5" in text             # model
    assert "8000" in text                        # cap / this call's size
    assert "do-not-raise" in text
    assert "raise the ceiling" not in text.lower()
    _assert_fenced(text, "theme_discovery", "output_ceilings")
    _assert_fenced_lines_are_short(text)

    audit.assert_awaited_once()
    detail = audit.await_args.args[2]
    assert "do-not-raise" in detail


def test_live_alert_flags_theme_validation_as_an_input_anomaly(monkeypatch):
    """theme_validation truncates live with enormous headroom: the alert must
    point at the input, not prescribe a raise."""
    st, audit, tg = _wire_live_alarm(monkeypatch, 31.0, 580)

    asyncio.run(st._maybe_alert_truncation(
        caller="theme_validation", model="claude-sonnet-5", output_tokens=1000))

    tg.assert_awaited_once()
    text = tg.await_args.args[0]
    assert "theme_validation" in text
    assert "1000" in text
    assert "AMPLE HEADROOM" in text
    assert "31" in text and "580" in text
    assert "do-not-raise" not in text
    _assert_fenced(text, "theme_validation")
    _assert_fenced_lines_are_short(text)


# ── 4. cost_board's NIGHTLY digest — end to end, DB-sourced per-caller diagnosis ───────────

class _FakeNightlyConn:
    """Two `fetch` shapes come off the same conn: the main per-caller aggregate
    (filtered by the instrumentation floor) and the new all-time history lookup
    for just the truncating callers. Distinguished by SQL shape, the way Postgres
    itself would answer two different queries."""

    def __init__(self, floor, agg_rows, hist_rows):
        self._floor, self._agg_rows, self._hist_rows = floor, agg_rows, hist_rows

    async def fetchval(self, sql, *args):
        assert "min(created_at)" in sql
        return self._floor

    async def fetch(self, sql, *args):
        if "caller = ANY($1)" in sql:
            wanted = set(args[0])
            assert "created_at" not in sql, (
                "the history lookup must be all-time — a lookback window here "
                "would misjudge a caller's TYPICAL peak on a quiet window")
            return [r for r in self._hist_rows if r["caller"] in wanted]
        assert "created_at >= $2" in sql
        return self._agg_rows


class _FakeNightlyPool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        conn = self._conn

        class _Ctx:
            async def __aenter__(self):
                return conn

            async def __aexit__(self, *a):
                return False
        return _Ctx()


def _wire_nightly(monkeypatch, agg_rows, hist_rows=()):
    from datetime import datetime, timezone
    from agents.market_intelligence import cost_board as cb

    floor = datetime(2026, 8, 1, tzinfo=timezone.utc)
    conn = _FakeNightlyConn(floor, agg_rows, list(hist_rows))

    async def _fake_get_pool():
        return _FakeNightlyPool(conn)
    monkeypatch.setattr(cb, "get_pool", _fake_get_pool)
    return cb


def _truncating_scenario(monkeypatch):
    return _wire_nightly(
        monkeypatch,
        agg_rows=[
            {"caller": "theme_discovery", "calls": 9, "truncated": 2, "unreported": 0,
             "cap_hit": 8000, "max_completed": 6700},
            {"caller": "ep_catalyst_grade", "calls": 300, "truncated": 2, "unreported": 0,
             "cap_hit": 1500, "max_completed": 140},
        ],
        hist_rows=[
            {"caller": "theme_discovery", "mean_completed": 6100.0, "max_completed": 6700},
            {"caller": "ep_catalyst_grade", "mean_completed": 65.0, "max_completed": 140},
        ],
    )


def test_nightly_check_attaches_a_diagnosis_per_truncating_caller(monkeypatch):
    cb = _truncating_scenario(monkeypatch)
    out = asyncio.run(cb.compute_truncation_check())

    by_caller = {x["caller"]: x for x in out["truncating"]}
    assert set(by_caller) == {"theme_discovery", "ep_catalyst_grade"}

    assert "do-not-raise" in by_caller["theme_discovery"]["diagnosis"]
    assert "6700" in by_caller["theme_discovery"]["diagnosis"]

    assert "AMPLE HEADROOM" in by_caller["ep_catalyst_grade"]["diagnosis"]
    assert "65" in by_caller["ep_catalyst_grade"]["diagnosis"]


def test_nightly_telegram_message_carries_the_diagnosis_not_the_blanket_advice(monkeypatch):
    cb = _truncating_scenario(monkeypatch)
    audit = AsyncMock()
    tg = AsyncMock(return_value=True)
    monkeypatch.setattr(cb, "log_audit_event", audit)
    import agents.market_intelligence.briefing as briefing_mod
    monkeypatch.setattr(briefing_mod, "send_telegram_message", tg)

    asyncio.run(cb.run_truncation_check())

    tg.assert_awaited_once()
    text = tg.await_args.args[0]
    assert "theme_discovery" in text and "ep_catalyst_grade" in text
    assert "do-not-raise" in text
    assert "AMPLE HEADROOM" in text
    assert "Raise the ceiling on these callers" not in text
    _assert_fenced(text, "theme_discovery", "ep_catalyst_grade")
    _assert_fenced_lines_are_short(text)


def test_nightly_near_ceiling_footer_also_respects_do_not_raise(monkeypatch):
    """narrative_theme_discovery's own registry entry predicts it hits the
    NEAR-CEILING arm before it ever truncates — this must not tell the operator
    to raise a cap the do-not-raise list forbids raising. Non-listed callers in
    the same footer still get the ordinary "raise before it cuts" advice.

    TWO callers per bucket (not one): a comma-joined caller list grows with
    caller count and was the exact shape of a prior regression here (a joined
    line stayed under the width guard with one caller per bucket and only broke
    it with a second) — this fixture makes the width assert load-bearing.
    """
    caps = {c: oc.max_tokens_for(c) for c in
            ("narrative_theme_discovery", "theme_split", "postmortem",
             "system_review_weekly")}
    assert oc.DO_NOT_RAISE_FOR_AT_CAP_PRESSURE >= {"narrative_theme_discovery", "theme_split"}
    assert not oc.DO_NOT_RAISE_FOR_AT_CAP_PRESSURE & {"postmortem", "system_review_weekly"}

    cb = _wire_nightly(monkeypatch, agg_rows=[
        {"caller": c, "calls": 50, "truncated": 0, "unreported": 0,
         "cap_hit": None, "max_completed": int(cap * 0.95)}
        for c, cap in caps.items()
    ])
    audit = AsyncMock()
    tg = AsyncMock(return_value=True)
    monkeypatch.setattr(cb, "log_audit_event", audit)
    import agents.market_intelligence.briefing as briefing_mod
    monkeypatch.setattr(briefing_mod, "send_telegram_message", tg)

    asyncio.run(cb.run_truncation_check())

    tg.assert_awaited_once()
    text = tg.await_args.args[0]
    assert "NEAR CEILING" in text
    for c in caps:
        assert c in text
    assert "don't raise" in text
    do_not_raise_block = text.split("don't raise):")[1].split("raise before they cut:")[0]
    assert "narrative_theme_discovery" in do_not_raise_block
    assert "theme_split" in do_not_raise_block
    raisable_block = text.split("raise before they cut:")[1]
    assert "postmortem" in raisable_block
    assert "system_review_weekly" in raisable_block
    _assert_fenced(text, *caps)
    _assert_fenced_lines_are_short(text)
