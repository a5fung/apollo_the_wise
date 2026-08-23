"""Regression lock for scripts/live_rules.py — the acting-rules view (built 2026-08-23).

The tool exists because three failures in one day asserted prose over ground truth:
a doc said "not yet deployed" for a live 2R stop, a doc said "flag OFF" for a four-weeks-live
env flag, and the day-3/5 partial path was read while the ACTING intraday path was not.
These tests pin the five behaviours that prevent each recurrence:

  1. a doc claiming "not yet deployed / flag OFF" while the thing IS acting → drift IS reported;
  2. an env var set in prod OVERRIDES the code default (and unset ≠ off);
  3. the EXIT section names BOTH partial paths and which one acts;
  4. prod unreachable → graceful degradation: rows labelled unknown, never guessed, exit clean;
  5. a dated change-log entry is historical ONLY when a LATER entry re-states its subject —
     the doc's most recent word on a subject is scanned like current prose, and a masked
     status claim naming no checkable flag surfaces UNVERIFIED, never silently dropped.

Synthetic fixtures only — no SSH, no live repo docs are asserted on (those change legitimately).
"""
from pathlib import Path

import pytest

from scripts.live_rules import (
    ConstFact,
    ProdState,
    Resolver,
    ToggleFact,
    build_exit_section,
    build_report,
    collect_code_facts,
    collect_prod,
    load_doc,
    parse_module_constants,
    parse_prod_capture,
    scan_live_comments,
    scan_stale_claims,
    scan_unrecorded_flips,
)


# ── fixtures ─────────────────────────────────────────────────────────────────

def _resolver(prod: ProdState | None = None, extra_code: dict | None = None) -> Resolver:
    code = {
        "REGIME_SIZING_ENABLED": ConstFact(
            name="REGIME_SIZING_ENABLED", module="agents/market_intelligence/constants.py",
            kind="env", env_var="REGIME_SIZING_ENABLED", cast="bool", value=False),
        "PROFIT_TRIGGER_R": ConstFact(
            name="PROFIT_TRIGGER_R", module="agents/market_intelligence/constants.py",
            kind="literal", value=2.0),
    }
    code.update(extra_code or {})
    toggles = {
        "breakeven_at_broker": ToggleFact(name="breakeven_at_broker", style="state",
                                          default=False, where="broker/order_manager.py:91"),
    }
    return Resolver(code, toggles, prod if prod is not None else ProdState(error="test: no prod"))


def _doc(tmp_path: Path, text: str) -> object:
    p = tmp_path / "synthetic_setup.md"
    p.write_text(text)
    return load_doc(p)


PROD_ON = ProdState(
    reachable=True,
    env={"apollo-market": {"REGIME_SIZING_ENABLED": "true"},
         "apollo-execution": {"REGIME_SIZING_ENABLED": "true"}},
    toggles=[{"safeguard": "breakeven_at_broker", "account_mode": "live",
              "state": "on", "last_transition_at": "2026-08-10 21:15:16+00"}],
)


# ── 1. a stale "not yet deployed / flag OFF" claim IS reported as drift ──────

def test_not_yet_deployed_claim_is_reported_even_without_a_checkable_flag(tmp_path):
    """The magna53 2026-08-23 shape: a deployment-status assertion naming NO flag. The tool must
    surface it (UNVERIFIED) rather than silently trust it — these are exactly the lines that rot."""
    doc = _doc(tmp_path, (
        "# Synthetic setup\n\n"
        "## Definition\n\n"
        "The stop is the 2R stop.\n"
        "⚠ Built, NOT yet deployed — the running image still places the old stop until the next deploy.\n"
    ))
    rows = scan_stale_claims(doc, _resolver())
    assert any("NOT yet deployed" in r.claim for r in rows), rows
    assert all(r.severity in ("UNVERIFIED", "DRIFT", "UNKNOWN") for r in rows)


def test_flag_off_claim_resolves_against_prod_env_and_reports_drift(tmp_path):
    """The safeguards 2026-08-23 shape: 'flag OFF by default' while the env flag is true in both
    containers. With the flag resolvable, the row must be a hard DRIFT naming the flag."""
    doc = _doc(tmp_path, (
        "# Synthetic setup\n\n"
        "## Position sizing\n\n"
        "**Phase**: code shipped behind a feature flag, flag OFF by default — production behaviour unchanged.\n\n"
        "**Flag**: `REGIME_SIZING_ENABLED` (env var, default `false`).\n"
    ))
    rows = scan_stale_claims(doc, _resolver(prod=PROD_ON))
    drift = [r for r in rows if r.severity == "DRIFT"]
    assert drift, rows
    assert "REGIME_SIZING_ENABLED" in drift[0].actual


def test_flag_off_claim_with_flag_actually_off_is_not_drift(tmp_path):
    """No crying wolf: the same claim while the flag really is off produces no DRIFT row."""
    prod_off = ProdState(reachable=True,
                         env={"apollo-market": {"REGIME_SIZING_ENABLED": None},
                              "apollo-execution": {"REGIME_SIZING_ENABLED": None}})
    doc = _doc(tmp_path, (
        "# Synthetic setup\n\n"
        "## Position sizing\n\n"
        "**Phase**: shipped behind a feature flag, flag OFF by default.\n\n"
        "**Flag**: `REGIME_SIZING_ENABLED` (env var, default `false`).\n"
    ))
    rows = scan_stale_claims(doc, _resolver(prod=prod_off))
    assert not [r for r in rows if r.severity == "DRIFT"], rows


def test_superseded_change_log_entry_is_historical_not_a_stale_claim(tmp_path):
    """'Built OFF' in a dated entry whose subject a LATER dated entry re-states is genuine
    history — never a drift row (the old blanket mask, now earned by supersession)."""
    doc = _doc(tmp_path, (
        "# Synthetic setup\n\n"
        "## Change log (newest first)\n\n"
        "### 2026-08-05 — regime sizing set true in prod (operator-signed)\n\n"
        "`REGIME_SIZING_ENABLED=true` set in both containers.\n\n"
        "### 2026-08-01 — thing BUILT (shipped OFF; operator-signed)\n\n"
        "**Flag**: `REGIME_SIZING_ENABLED`. Built OFF, awaiting sign-off.\n"
    ))
    assert scan_stale_claims(doc, _resolver(prod=PROD_ON)) == []


def test_unsuperseded_change_log_claim_is_scanned_like_current_prose(tmp_path):
    """The 2026-08-23 regression shape REBORN INSIDE THE MASK: a dated entry is the doc's most
    recent word on its subject ('Built OFF') while the flag IS acting → a hard DRIFT row.
    The blanket historical exemption hid 45 of 59 status-shaped lines from the scanner."""
    doc = _doc(tmp_path, (
        "# Synthetic setup\n\n"
        "## Change log (newest first)\n\n"
        "### 2026-08-01 — thing BUILT (shipped OFF; operator-signed)\n\n"
        "**Flag**: `REGIME_SIZING_ENABLED`. Built OFF, awaiting sign-off.\n"
    ))
    rows = scan_stale_claims(doc, _resolver(prod=PROD_ON))
    drift = [r for r in rows if r.severity == "DRIFT"]
    assert drift, rows
    assert "REGIME_SIZING_ENABLED" in drift[0].actual


def test_masked_status_claim_without_identifier_is_reported_unverified(tmp_path):
    """A deployment-status claim in a dated entry naming NO checkable flag, with no later entry
    superseding it, must surface as UNVERIFIED (historical, unsuperseded) — never silently
    dropped. This is the exact shape of safeguards.md:462 (2026-08-23), stale within hours."""
    doc = _doc(tmp_path, (
        "# Synthetic setup\n\n"
        "## Change log (newest first)\n\n"
        "### 2026-08-10 — widget rework\n\n"
        "**Status**: shipped to the working tree, not yet deployed — needs the next deploy window.\n"
    ))
    rows = scan_stale_claims(doc, _resolver(prod=PROD_ON))
    assert any(r.severity == "UNVERIFIED" and "unsuperseded" in r.actual for r in rows), rows


def test_value_transition_arrow_is_checked_against_the_post_arrow_value(tmp_path):
    """`NAME = 60 → 10` in an unsuperseded dated entry claims the CURRENT value is 10 — the scan
    must compare the post-arrow value, not flag the recorded old one."""
    from scripts.live_rules import scan_value_mismatches
    text = (
        "# Synthetic setup\n\n"
        "## Change log (newest first)\n\n"
        "### 2026-05-04 — retry delay dropped\n\n"
        "`BAR_RETRY_DELAY_SEC = 60 → 10`.\n"
    )
    matching = {"BAR_RETRY_DELAY_SEC": ConstFact(
        name="BAR_RETRY_DELAY_SEC", module="m.py", kind="literal", value=10)}
    doc = _doc(tmp_path, text)
    assert scan_value_mismatches([doc], _resolver(extra_code=matching)) == []
    drifted = {"BAR_RETRY_DELAY_SEC": ConstFact(
        name="BAR_RETRY_DELAY_SEC", module="m.py", kind="literal", value=12)}
    rows = scan_value_mismatches([doc], _resolver(extra_code=drifted))
    assert rows and rows[0].claim == "BAR_RETRY_DELAY_SEC=10", rows


def test_unrecorded_toggle_flip_is_reported(tmp_path):
    """A mi_safeguard_state toggle ON in prod whose every doc mention still reads 'DEFAULT OFF'
    → the flip was never recorded in the SSoT (missing the row does NOT mean off)."""
    doc = _doc(tmp_path, (
        "# Synthetic setup\n\n"
        "## Change log (newest first)\n\n"
        "### 2026-08-08 — breakeven at the broker SHIPPED DARK\n\n"
        "Gated on `breakeven_at_broker`, DEFAULT OFF.\n"
    ))
    rows = scan_unrecorded_flips([doc], _resolver(prod=PROD_ON))
    assert any("breakeven_at_broker" in r.claim for r in rows), rows


def test_live_comment_without_changelog_entry_is_reported():
    """A `# LIVE <date>` code comment with no setup change-log entry dated that day → drift.
    (Run against the real repo tree with an empty date set to prove the rule fires; the real
    run uses the real dates, where constants.py's 2026-08-01 IS recorded in exit_discipline.md.)"""
    rows = scan_live_comments([], changelog_dates=set())
    assert any(r.where.startswith("agents/market_intelligence/constants.py") for r in rows), rows


# ── 2. env var overrides code default ────────────────────────────────────────

def test_env_var_set_in_prod_overrides_code_default():
    res = _resolver(prod=PROD_ON)
    r = res.const("REGIME_SIZING_ENABLED")
    assert r.value is True and r.known
    assert "prod env" in r.source


def test_env_var_unset_in_prod_falls_back_to_code_default_and_says_so():
    prod = ProdState(reachable=True,
                     env={"apollo-market": {"REGIME_SIZING_ENABLED": None},
                          "apollo-execution": {"REGIME_SIZING_ENABLED": None}})
    r = _resolver(prod=prod).const("REGIME_SIZING_ENABLED")
    assert r.value is False and r.known
    assert "env unset in prod" in r.source


def test_env_parse_recognises_bool_and_cast_and_default_ref_patterns():
    facts = parse_module_constants(
        'import os\n'
        '_D = 9.0\n'
        'GAP = float(os.environ.get("EP_MIN_GAP_PCT", _D))\n'
        'FLAG = os.environ.get("MY_FLAG", "false").lower() == "true"\n',
        "m.py")
    assert facts["GAP"].kind == "env" and facts["GAP"].value == 9.0
    assert facts["FLAG"].kind == "env" and facts["FLAG"].value is False


# ── 3. the EXIT section shows BOTH partial paths and which one acts ──────────

def test_exit_section_names_both_partial_paths_and_the_acting_one():
    """Listing one partial path is the exact 2026-08-23 failure — both must always appear,
    with the intraday trigger ACTING and the day-3/5 gate STANDING DOWN while it is on."""
    code = collect_code_facts()
    res = Resolver(code, {}, ProdState(error="test: offline"))
    text = "\n".join(build_exit_section(res))
    assert "scan_profit_triggers" in text
    assert "run_partial_exits" in text
    ptr = code.get("PROFIT_TRIGGER_R")
    if ptr is not None and ptr.value:
        assert "ACTING" in text and "STANDING DOWN" in text
    else:  # trigger reverted to None → the time gate must be shown as the acting path
        assert "ACTING" in text


# ── 4. graceful degradation when prod is unreachable ─────────────────────────

def test_prod_unreachable_degrades_to_labelled_unknowns_not_guesses():
    def failing_runner(cmd):
        raise TimeoutError("no route to host")

    prod = collect_prod(["REGIME_SIZING_ENABLED"], runner=failing_runner)
    assert prod.reachable is False and "TimeoutError" in prod.error

    res = _resolver(prod=prod)
    r = res.const("REGIME_SIZING_ENABLED")
    assert r.known is False and "UNREACHABLE" in r.source

    # The full report still renders, says prod is unreachable, and exits nowhere.
    report = build_report(res, [], [], drift_only=True)
    assert "UNREACHABLE" in report


def test_secret_named_env_vars_are_never_requested_from_prod():
    captured: list[str] = []

    def runner(cmd):
        captured.append(cmd[-1])  # the server-side script
        return ""

    collect_prod(["REGIME_SIZING_ENABLED", "ALPACA_LIVE_API_KEY", "POSTGRES_PASSWORD",
                  "TELEGRAM_BOT_TOKEN", "INTERNAL_API_SECRET"], runner=runner)
    script = captured[0]
    assert "REGIME_SIZING_ENABLED" in script
    for secret in ("ALPACA_LIVE_API_KEY", "POSTGRES_PASSWORD", "TELEGRAM_BOT_TOKEN",
                   "INTERNAL_API_SECRET"):
        assert secret not in script


def test_parse_prod_capture_roundtrip():
    raw = (
        "===ENV:apollo-market===\n"
        "REGIME_SIZING_ENABLED=true\n"
        "EP_MIN_GAP_PCT(unset)\n"
        "===TOGGLES===\n"
        "breakeven_at_broker|live|on|2026-08-10 21:15:16+00\n"
        "===STRATEGIES===\n"
        "magna53|live|t|t|1.0\n"
        "===DEPLOYED_COMMIT===\n"
        "abc123 2026-08-23T07:22:22-07:00 some subject\n"
    )
    st = parse_prod_capture(raw)
    assert st.reachable
    assert st.env["apollo-market"]["REGIME_SIZING_ENABLED"] == "true"
    assert st.env["apollo-market"]["EP_MIN_GAP_PCT"] is None
    assert st.toggle_row("breakeven_at_broker", "live")["state"] == "on"
    assert st.strategies[0]["live_real_enabled"] is True
    assert st.deployed_commit.startswith("abc123")
