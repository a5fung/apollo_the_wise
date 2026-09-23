"""#513 — the monthly sweep digest must lead with DECISIONS, not raw tables.

Operator 2026-08-01, reading the 8/01 sweep: *"it contains so much info, not all formatted well,
and I have no idea what to do with it… so only option is paste it here."*

The defect was RENDERING, not content. Thirteen scripts each pasted a raw table, and the two items
that actually needed him were buried mid-message: four M&A-suppressed movers (CLRO +358%) and two
judge demotions that then ran.

**The invariant these tests exist to hold: a check whose output cannot be classified must NEVER be
reported as clean.** A digest that says "all clear" because it failed to parse is the exact failure
this rewrite removes.
"""
from datetime import datetime, timezone

from agents.market_intelligence import quarterly_review as qr

_T = datetime(2026, 8, 1, 22, 0, tzinfo=timezone.utc)


def _r(label, stdout, code=0, module="agents.market_intelligence.probes.x"):
    return {"label": label, "module": module, "exit_code": code,
            "stdout_summary": stdout, "stderr_tail": ""}


# ── classification ───────────────────────────────────────────────────────────────────────────

def test_operator_markers_route_to_needs_your_call():
    for marker in ("MATERIAL-MISS CANDIDATE", "For OPERATOR labeling", "HARD-gate"):
        assert qr._classify(f"blah\n{marker}\nblah")[0] == "you", marker


def test_concluded_markers_route_to_done():
    for marker in ("STRUCTURAL NO-GO", "NO-SHIP", "No drift events detected"):
        assert qr._classify(f"x\n{marker}\ny")[0] == "done", marker


def test_accrual_markers_route_to_waiting():
    assert qr._classify("N = 5 < 10. INSUFFICIENT for ship")[0] == "waiting"
    assert qr._classify("promotion gate: ACCRUING (3/10 settled)")[0] == "waiting"


def test_unclassifiable_output_is_REVIEW_not_clean():
    """The load-bearing one. Silence must not read as a pass."""
    assert qr._classify("some table nobody taught me to read")[0] == "review"


def test_empty_output_is_review_not_clean():
    assert qr._classify("")[0] == "review"
    assert qr._classify("   \n  ")[0] == "review"


def test_operator_marker_wins_over_a_concluded_marker():
    """A script can print both. Anything needing him must never be buried under a green verdict."""
    assert qr._classify("VERDICT: GO\nMATERIAL-MISS CANDIDATE here")[0] == "you"


# ── rendering ────────────────────────────────────────────────────────────────────────────────

def test_decisions_come_first_and_before_everything_else():
    out = qr._render_digest(
        [_r("M&A accuracy", "CLRO +358%  <-- MATERIAL-MISS CANDIDATE (verify FP)"),
         _r("News quality", "✅ No drift events detected.")], _T, 46.0)
    assert out.index("NEEDS YOUR CALL") < out.index("Everything else")
    assert "M&A accuracy" in out.split("Everything else")[0]


def test_no_raw_tables_reach_the_message():
    """The whole complaint. A 1,500-char table dump must not survive into the digest."""
    table = "\n".join(f"  BAND {i}   n={i}   avg_5d +{i}.0%   win {i}/10" for i in range(40))
    out = qr._render_digest([_r("Revenue bands", table)], _T, 5.0)
    assert "BAND 7" not in out and "avg_5d" not in out
    assert len(out) < 900


def test_says_none_explicitly_when_nothing_needs_him():
    out = qr._render_digest([_r("News quality", "✅ No drift events detected.")], _T, 3.0)
    assert "NEEDS YOUR CALL* — none" in out


def test_failed_scripts_are_surfaced_not_swallowed():
    out = qr._render_digest(
        [{"label": "Broken", "module": "m", "exit_code": 1,
          "stdout_summary": "", "stderr_tail": "ImportError: boom"}], _T, 1.0)
    assert "FAILED TO RUN" in out and "Broken" in out


def test_money_line_is_lifted_and_surfaced():
    out = qr._render_digest(
        [_r("Judge", "💵 Realized (alerts that became trades): traded 36 · total P&L $-226")],
        _T, 2.0)
    assert "traded 36" in out and "$-226" in out


def test_every_check_appears_somewhere():
    """Decision-first must not mean checks vanish — nothing stops being reported."""
    rs = [_r("A", "MATERIAL-MISS CANDIDATE"), _r("B", "STRUCTURAL NO-GO"),
          _r("C", "ACCRUING"), _r("D", "unparseable")]
    out = qr._render_digest(rs, _T, 9.0)
    for label in ("A", "B", "C", "D"):
        assert f" {label} " in out or f"• {label} " in out or f"{label} —" in out


def test_points_at_the_audit_surface_for_detail():
    out = qr._render_digest([_r("X", "MATERIAL-MISS CANDIDATE")], _T, 1.0)
    assert "/audit" in out
