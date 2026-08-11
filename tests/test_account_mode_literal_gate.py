"""Regression lock for the account-mode-literal gate + graduation sweep (2026-08-11).

The rot class (operator, 2026-08-11): a query hardcoding `account_mode = 'paper'`
is correct the day it ships and silently reads a dead book the day the strategy
graduates — `get_flag_universe` path (c) sat dark ~7 weeks after MAGNA53 went live
2026-06-22 (17 live R3 rows invisible vs 1 paper). A static ban alone cannot catch
the rot (the literal is CORRECT at ship time), so the fix is two halves sharing one
scanner:

1. Deploy gate [5o/7] (`scripts/preflight_account_mode_literals.py`): every
   account-mode/phase literal in production SQL must carry a reviewed `mode-ok:`
   escape — the complete, greppable INVENTORY of book-pins.
2. Nightly `run_account_mode_graduation_sweep` (health_checks): replays that
   inventory at the only moments rot can happen — an `mi_strategies.phase` change
   (announced once; the audit-log snapshot advancing is the dedupe) or a pinned
   book going dormant while another moves (announced once per book EVER — the
   dead-column sweep pattern). Silent on a healthy day.

These tests lock: the scanner's detection + escape + docstring/comment/kwarg
exemptions (mutation-proven on synthetic sources), the CURRENT TREE staying clean
(the gate's exit-0 contract, enforced in CI not just at deploy), the sweep's
once-ever dedupe + fail-open structure, the wiring (scheduler + deploy.sh), and
the live_tracker fix this sweep found (the third skip-writer that defaulted to
the legacy paper mode).
"""
import pathlib

from scripts.preflight_account_mode_literals import (
    collect_pinned_sites, scan_source, sites_pinned_to,
)

HEALTH = pathlib.Path("agents/market_intelligence/health_checks.py").read_text(encoding="utf-8")
SCHED = pathlib.Path("agents/market_intelligence/scheduler.py").read_text(encoding="utf-8")
DEPLOY = pathlib.Path("scripts/deploy.sh").read_text(encoding="utf-8")
TRACKER = pathlib.Path("agents/market_intelligence/broker/live_tracker.py").read_text(encoding="utf-8")


# ── the scanner CATCHES the bug class (mutation proofs) ─────────────────────

def test_flags_the_exact_known_case_shape():
    """The literal that went dark for 7 weeks must flag without an escape."""
    src = (
        "async def f(conn):\n"
        "    return await conn.fetch('''\n"
        "        SELECT ticker FROM mi_live_trades\n"
        "        WHERE status = 'closed'\n"
        "          AND account_mode = 'paper'\n"
        "    ''')\n"
    )
    hits = scan_source(src, "<test>")
    assert len(hits) == 1
    assert hits[0]["text"] == "account_mode = 'paper'"
    assert not hits[0]["escaped"]
    assert hits[0]["line"] == 5, "lineno must point at the literal, not the string start"


def test_flags_phase_literals_too():
    hits = scan_source('q = "SELECT 1 FROM mi_strategies WHERE phase = \'live\'"\n', "<t>")
    assert len(hits) == 1 and hits[0]["text"] == "phase = 'live'"


def test_sql_comment_escape_is_honored():
    src = (
        "q = '''\n"
        "    WHERE account_mode = 'live'  -- mode-ok: real-money book by design\n"
        "'''\n"
    )
    hits = scan_source(src, "<t>")
    assert len(hits) == 1 and hits[0]["escaped"]


def test_python_comment_escape_is_honored():
    src = "clauses.append(\"account_mode = 'live'\")  # mode-ok: #447\n"
    hits = scan_source(src, "<t>")
    assert len(hits) == 1 and hits[0]["escaped"]


# ── the scanner does NOT cry wolf (a guard that always fires is not a guard) ──

def test_docstrings_are_exempt():
    src = (
        "def f():\n"
        '    """Sweeps account_mode=\'live\' rows — paper is deliberately excluded."""\n'
        "    return 1\n"
    )
    assert scan_source(src, "<t>") == []


def test_comment_lines_are_exempt():
    assert scan_source("# the old query said account_mode = 'paper'\nx = 1\n", "<t>") == []


def test_python_kwargs_are_exempt():
    """account_mode="paper" plumbing (mode explicit at the call site) is not a
    hidden book-pin — double-quoted kwargs must not flag."""
    assert scan_source('await client.get_order(oid, account_mode="paper")\n', "<t>") == []


def test_sites_pinned_to_filters_by_book():
    src = (
        "a = \"WHERE account_mode = 'paper'\"\n"
        "b = \"WHERE account_mode = 'live'\"\n"
    )
    hits = scan_source(src, "<t>")
    assert [s["text"] for s in sites_pinned_to("paper", hits)] == ["account_mode = 'paper'"]


# ── the CURRENT TREE is clean (the gate's exit-0 contract, locked in CI) ────

def test_tree_has_zero_unannotated_literals():
    """Every production account-mode/phase literal carries a reviewed mode-ok
    escape. A new unannotated pin fails HERE (CI/pre-push), not just at deploy."""
    unannotated = [s for s in collect_pinned_sites() if not s["escaped"]]
    assert unannotated == [], (
        "hardcoded account-mode/phase literal(s) without a reviewed 'mode-ok:' "
        f"escape (the get_flag_universe 7-weeks-dark rot class): "
        f"{[(s['file'], s['line'], s['text']) for s in unannotated]}"
    )


def test_no_query_pins_the_paper_book_today():
    """2026-08-11 ground truth: there are NO active paper setups (operator), so no
    production query may filter to account_mode='paper' — annotated or not. If a
    paper phase ever returns, this test is the reviewed place to relax that."""
    paper_pins = [s for s in sites_pinned_to("paper")
                  if s["text"].startswith("account_mode")]
    assert paper_pins == [], (
        f"query pinned to the dormant paper book: "
        f"{[(s['file'], s['line']) for s in paper_pins]}"
    )


# ── the graduation sweep structure ──────────────────────────────────────────

def _sweep() -> str:
    i = HEALTH.find("ACCOUNT-MODE GRADUATION SWEEP")
    assert i > 0, "the graduation sweep is gone"
    assert "async def run_account_mode_graduation_sweep" in HEALTH[i:]
    return HEALTH[i:]


def test_sweep_announces_a_dormant_book_ONCE_EVER():
    """The dead-column pattern: the audit log IS the dedupe state, so a dormant
    book cannot become a nightly nag (the failure mode that gets guards muted)."""
    body = _sweep()
    assert "account_mode_book_dormant" in body
    assert "already" in body and "key in already" in body


def test_sweep_snapshot_is_the_transition_dedupe():
    """Phase transitions announce because the stored phase map differs from the
    current one; advancing the snapshot in the same run makes it once-per-change."""
    body = _sweep()
    assert "strategy_phase_snapshot" in body
    assert "strategy_phase_transition" in body
    assert body.count("_GRAD_SNAPSHOT_EVENT, fingerprint") >= 2, (
        "the snapshot must advance on both the baseline AND the transition path")


def test_sweep_first_run_is_SILENT():
    """Baselining a fresh DB must not Telegram the whole registry as 'news'."""
    body = _sweep()
    assert 'out["baseline"] = True' in body


def test_sweep_dormancy_needs_ANOTHER_active_book():
    """All books quiet = outage/halt, not a graduation — must not fire."""
    body = _sweep()
    assert "if not active:" in body


def test_sweep_ignores_books_with_no_pinned_queries():
    """The paper book going dormant after graduation is the EXPECTED end state;
    it only matters if code still reads it."""
    body = _sweep()
    assert "if not pinned:" in body


def test_sweep_inventory_comes_from_the_gate_scanner():
    """One scanner, two moments: the checklist replayed at graduation must be
    exactly the inventory the deploy gate enforces."""
    assert "from scripts.preflight_account_mode_literals import collect_pinned_sites" in HEALTH


def test_sweep_is_wired_into_the_nightly_audit():
    assert "run_account_mode_graduation_sweep" in SCHED


def test_gate_is_wired_into_deploy():
    assert "preflight_account_mode_literals" in DEPLOY


# ── the live find this sweep exists to prevent ──────────────────────────────

def test_orb_filter_skip_writer_threads_the_strategy_mode():
    """live_tracker.process_new_alerts_live was the THIRD skip-writer defaulting
    to current_account_mode() (= 'paper' on prod via the legacy ALPACA_PAPER env)
    after the other two were fixed 7/8 — latent only because no filter:* skip has
    ever fired in prod. The insert must thread the resolved MAGNA53 mode."""
    i = TRACKER.find("async def process_new_alerts_live")
    assert i > 0
    j = TRACKER.find("passed, skip_reason = await check_filters", i)
    assert j > 0
    call_end = TRACKER.find(")", TRACKER.find("_insert_skipped_trade", j))
    call = TRACKER[j:call_end]
    assert "account_mode=_magna53_mode" in call, (
        "the check_filters skip insert dropped its account_mode again — it will "
        "write live-strategy skips into the dormant paper book")
