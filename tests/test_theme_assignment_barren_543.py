"""The theme-assignment stage was DEAD for ten days and nothing said so (#543, 2026-08-07).

Every `theme_assignment` call from 07-28 to 08-07 returned exactly its 4000-token ceiling and
ended in either "proposed 0 assignment(s)" (11x) or `assignment_silent_stop` (2x). Not one
successful assignment in the window — while the board carried 91 themes averaging 3.2 members and
an entire gapping software cohort belonged to no theme at all.

It hid because **"proposed 0 assignments" is a telemetry line, not an error.** A total outage of
the stage that puts stocks INTO themes reads exactly like a quiet night. The operator found it by
asking; nothing in the system told anyone. His words: *"we really need to figure out how we can
miss this, a complete outage, and it's a bug we've seen before, unacceptable."*

It IS a bug we had seen before: `max_tokens` was raised 1000 → 4000 in May 2026 for this same
failure — the model spending its whole budget on prose before reaching the tool call. Raising the
ceiling bought three months. So the fix is structural (`tool_choice="any"` makes free text unable
to consume the budget) and these tests pin the DETECTION, which is what was actually missing.

The signature is deliberately about a STREAK, not a night: zero assignments once is normal
(nothing needed re-homing); zero across three consecutive runs is a dead stage.
"""
import pathlib
import re

SRC = pathlib.Path("agents/market_intelligence/health_checks.py").read_text(encoding="utf-8")


def _assignment_call() -> dict:
    """The kwargs the assignment loop's messages.create call actually sends — captured from
    ONE nightly-shaped call through the real `_propose_assignment_batch` against a scripted
    client (2026-09-14: behaviour, not a source scan — the call site gained an EP-time caller
    with its own tool choice, and a text pin on the source could no longer name which one)."""
    import asyncio
    from agents.market_intelligence import theme_engine

    class _Block:
        def __init__(self, type_, name=None, input_=None, id="b1"):
            self.type, self.name, self.input, self.id = type_, name, input_ or {}, id

    class _Resp:
        def __init__(self, blocks):
            self.content, self.stop_reason = blocks, "tool_use"

    captured: dict = {}

    class _Messages:
        async def create(self, **kwargs):
            captured.update(kwargs)
            return _Resp([_Block("tool_use", name="assign_stocks_to_themes",
                                  input_={"assignments": []})])

    class _Client:
        messages = _Messages()

    async def _run():
        import agents.market_intelligence.spend_tracker as spend_mod
        _real_spend, _real_audit = spend_mod.log_anthropic_call_safe, theme_engine.log_audit_event

        async def _noop(*a, **k):
            return None
        spend_mod.log_anthropic_call_safe, theme_engine.log_audit_event = _noop, _noop
        try:
            await theme_engine._propose_assignment_batch(
                _Client(), [{"ticker": "AAA", "rs_composite": 90, "sector": "Technology"}],
                shared_prefix="Existing themes: (none)", cooldown_note="",
                advisor_state={"calls": 0}, batch_no=1, n_batches=1, pool_size=1)
        finally:
            spend_mod.log_anthropic_call_safe, theme_engine.log_audit_event = _real_spend, _real_audit
    asyncio.run(_run())
    assert captured, "theme_assignment call site not found"
    return captured


# ── the structural fix: free text can no longer eat the budget ───────────────────────────

def test_assignment_forces_a_tool_call():
    """`auto` let the model answer in prose and never reach a tool — which IS the failure path
    ("no tool_uses" below it). `any` makes that impossible rather than merely less likely."""
    call = _assignment_call()
    assert call.get("tool_choice") == {"type": "any"}, (
        "theme assignment no longer forces a tool call — the model can spend its whole budget on "
        "prose and silently produce nothing, which is the 07-28→08-07 outage")
    assert {t["name"] for t in call["tools"]} == {"assign_stocks_to_themes", "consult_advisor"}


def test_assignment_ceiling_was_raised_too():
    """Belt-and-braces for genuinely long assignment lists. Raising a cap costs nothing extra —
    billing is on tokens generated, not the ceiling."""
    # 2026-08-09: the number moved into the ceilings registry (with its evidence);
    # the call site must bind from there, and the registered value must hold.
    from shared.output_ceilings import max_tokens_for
    assert _assignment_call().get("max_tokens") == max_tokens_for("theme_assignment"), (
        "theme_assignment no longer binds its ceiling from shared/output_ceilings.py")
    assert max_tokens_for("theme_assignment") >= 8000, (
        f"assignment ceiling back down to {max_tokens_for('theme_assignment')}")


# ── the detection, which is the part that was actually missing ───────────────────────────

def test_a_barren_streak_signature_exists():
    assert "assignment_producing_nothing" in SRC, (
        "the barren-assignment signature is gone — a dead assignment stage is silent again")
    assert "theme_assignment_barren" in SRC, "the audit event for the outage is gone"


def test_it_keys_on_a_STREAK_not_a_single_night():
    """One quiet night is normal. Three consecutive is a dead stage. If this ever becomes a
    single-night check it will cry wolf nightly and get ignored — the failure mode that killed
    the LIKELY-BUILT surface."""
    assert "len(barren) >= 3" in SRC, "barren signature no longer requires a 3-night streak"


def test_nights_the_engine_did_not_run_do_not_count():
    """A weekend with no engine run is not a failure. Without this the check would fire every
    Monday."""
    assert "Only nights the stage actually RAN count" in SRC or "ran = [r for r in c_rows" in SRC, (
        "the barren signature no longer filters to nights the engine actually ran")


def test_the_streak_breaks_on_a_productive_night():
    """A night that DID produce assignments must reset the streak, or one bad patch alerts
    forever afterwards."""
    assert "break" in SRC.split("streak broken by a night")[0][-400:], (
        "the barren streak no longer breaks on a productive night")


def test_the_outage_alert_is_NOT_deduped():
    """The two lifecycle signatures dedupe per-theme, correctly. This one must not: it is a stage
    outage and must keep shouting every night until fixed. The original went silent for ten days
    precisely because its only trace looked routine."""
    seg = SRC.split("barren = summary.get")[1][:1800]
    assert "Deliberately NOT deduped" in seg, (
        "the barren alert appears to have been folded into the deduped path — a stage outage that "
        "announces once and then goes quiet is the bug, not the fix")


def test_it_fails_open_like_its_siblings():
    """A broken query in this signature must not blind the other two, and must not raise."""
    seg = SRC.split("assignment-barren signature failed")[0][-900:]
    assert "except Exception" in seg, "barren signature no longer isolated behind its own except"
