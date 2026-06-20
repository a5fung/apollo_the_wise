"""Filing-quality gate in check_plan.py (operator 2026-06-20): a task must be filed with
actionable detail + a clear outcome, never a placeholder bucket. The gate bans the exact
'confirm scope at triage' stub class that produced 13 contentless ghosts. Pins that the gate
catches the stub shape and does NOT false-positive on real (even terse) task descriptions."""
from scripts.check_plan import parse


def _errs(title: str) -> list[str]:
    text = f"## Stocks in Play\n- #999 | 2026-12-31 | pending | {title}\n"
    _, errors = parse(text)
    return [e for e in errors if "PLACEHOLDER" in e]


def test_catches_the_original_stub_titles():
    # the exact 13-ghost shape.
    assert _errs("(SiP backlog — confirm scope/title at triage)")
    assert _errs("(judge/catalyst item — confirm scope at triage)")
    assert _errs("(op-safety item — confirm scope at triage)")


def test_no_false_positive_on_real_tasks():
    # real task descriptions — even terse ones — must NOT trip the gate.
    assert not _errs("theme_engine isinstance(anthropic.APIError) TypeError — harden the guard")
    assert not _errs("RS liquidity floor — raise floor / cap-floor (gated, N>=10 + sign-off)")
    assert not _errs("Merge /setup + /why into one observability command")
    # 'confirm' alone (not 'confirm scope') and 'triage' alone (not 'at triage') are fine.
    assert not _errs("⚠ SCOPE THIN — EP-detection calibration; OPERATOR: confirm subsumed → close")
    assert not _errs("triage the idle data-gated reviews (run/defer/ratify each)")


# ── High-stakes pointer gate (operator 2026-06-20, the #305 lesson) ──
# A launch / real-money / cutover task must POINT at where its execution lives — the exact
# class that let #305 (the real-money GO) slip as a bare one-liner the stub-ban couldn't see.

def _hs(title: str) -> list[str]:
    text = f"## Launch\n- #999 | 2026-12-31 | pending | {title}\n"
    _, errors = parse(text)
    return [e for e in errors if "HIGH-STAKES" in e]


def test_high_stakes_without_a_pointer_is_blocked():
    # the #305 failure shape: a real-money/launch decision with no runbook/doc/#ref.
    assert _hs("🚀 6/22 GO/NO-GO decision with operator (NO-GO = launch-complete)")
    assert _hs("real-money cutover — flip magna53 to live and start small")
    assert _hs("go-live for the 9m_day2 strategy once promoted")


def test_high_stakes_with_any_legit_pointer_passes():
    # every legitimate pointer form clears it — a doc, a #task, a memory, or the SSoT.
    assert not _hs("🚀 GO/NO-GO + EXECUTE — runbook docs/roadmap/monday_go_runbook.md")
    assert not _hs("real-money cutover — see #305 for the full sequence")
    assert not _hs("PDT/Rule 4210 relax BLOCK_PDT_LOCKOUT via CHANGE_PROCESS (memory pdt_rule_4210_change_2026)")
    assert not _hs("go-live config flip — SSoT safeguards.md change-log carries the design")


def test_non_high_stakes_terse_task_is_not_touched():
    # the rule is NARROW: a terse non-high-stakes task without a pointer is fine
    # (broad 'adequate detail' is semantic and intentionally NOT gated — it over-flags).
    assert not _hs("shared scheduled_eod_digest helper (the ~6-job 16:xx digest family)")
    assert not _hs("regime engine: spy_vs_200ma NULL fix + stale docstring")


# ── CLOSE-ritual new-task DETAIL audit (operator 2026-06-20): looks_thin heuristic ──
# A SURFACE-for-review (not a hard gate) for tasks ADDED this session — it intentionally
# over-flags (detail is semantic), so we pin only the clear ends of the spectrum.

def test_looks_thin_flags_the_genuinely_thin():
    from scripts.check_plan import looks_thin
    # the #305-class contentless lines — including the self-ref edge case (#115 in its own line)
    assert looks_thin("/simplify deferral (filed #115)", 115)
    assert looks_thin("per-strategy sizing/cap follow-ups")


def test_looks_thin_clears_anything_with_a_real_signal():
    from scripts.check_plan import looks_thin
    assert not looks_thin("regime spy_vs_200ma NULL fix — see docs/setups/regime.md")  # file-ref
    assert not looks_thin("dedup the caches → one shared util, tests green")            # DoD arrow
    assert not looks_thin("detector boilerplate dedup (pairs with #116)")              # xref to ANOTHER task
    assert not looks_thin("x" * 125)                                                    # long enough to carry detail
