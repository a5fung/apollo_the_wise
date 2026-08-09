"""shared/output_ceilings.py — the ONE registry of max_tokens ceilings (2026-08-09).

Why this exists: 24+ hardcoded max_tokens numbers scattered across agents/, core/
and channels/ each rotted silently the moment the auto-tracked model resolver moved
a role to a new model (postmortem + system_review_weekly truncated on their FIRST
sonnet-5 calls; theme_advisor silently truncated 149/151 opus-4-8 calls at 600 for
two months). Auto-deriving the numbers was measured and rejected — truncated samples
are censored AT the cap, so exactly the callers that need a new number have zero
completed samples to derive it from (full analysis in the registry docstring).

These tests pin the three things that make the registry load-bearing rather than
decorative:
  1. integrity — every entry bounded, evidenced, and mapped to a real model role;
  2. the BUILD GATE — no new hardcoded max_tokens literal may appear at a call
     site in agents/ core/ channels/; new callers must register (with evidence);
  3. the detection arms — near-ceiling threshold sits in the measured gap, the
     by-design set is shared, the model-change sweep maps roles to callers.
"""
import ast
import pathlib

import pytest

from shared import llm_models
from shared import output_ceilings as oc

REPO = pathlib.Path(__file__).resolve().parents[1]
SCANNED_DIRS = ("agents", "core", "channels")


# ── 1. registry integrity ────────────────────────────────────────────────────────────────

def test_every_ceiling_is_positive_and_under_the_streaming_bound():
    """HARD_CAP = 16000 is the non-streaming SDK boundary (above ~16K output the SDK
    requires streaming to avoid HTTP timeouts) — a technical bound, not a preference.
    Anything larger is a deliberate streaming design, not a registry bump."""
    for caller, entry in oc.CEILINGS.items():
        assert 0 < entry.max_tokens <= oc.HARD_CAP, (
            f"{caller}: max_tokens={entry.max_tokens} outside (0, {oc.HARD_CAP}]")


def test_every_tracked_role_is_a_real_llm_models_constant():
    """The model-change sweep joins registry entries to mi_model_resolution rows BY
    ROLE NAME. A typo'd role would silently never match — the entry would look
    covered and never be flagged on a model change (the exact rot class again)."""
    for caller, entry in oc.CEILINGS.items():
        if entry.role is None:
            continue
        assert isinstance(getattr(llm_models, entry.role, None), str), (
            f"{caller}: role {entry.role!r} is not a shared.llm_models constant — "
            "the model-change sweep can never flag this ceiling")


def test_every_entry_carries_evidence():
    """A number without its measurement is a picked number. `sized_on` names the
    model the value was sized against; `evidence` is the one-line provenance."""
    for caller, entry in oc.CEILINGS.items():
        assert entry.sized_on.strip(), f"{caller}: sized_on is empty"
        assert len(entry.evidence.strip()) >= 20, f"{caller}: evidence is missing/thin"


def test_by_design_truncators_are_registered_and_tiny():
    """The exempt set must be a subset of the registry (an unregistered exempt name
    silently exempts nothing) and each must be a genuine ping-sized ceiling."""
    for caller in oc.TRUNCATION_BY_DESIGN:
        assert caller in oc.CEILINGS, f"{caller} exempt but not registered"
        assert oc.CEILINGS[caller].max_tokens <= 16, (
            f"{caller} is exempt from truncation alerts with a {oc.CEILINGS[caller].max_tokens}"
            "-token ceiling — by-design truncation is a ping property, not a blanket pass")


def test_lookup_is_loud_on_unknown_caller():
    """Call sites bind at import — a typo or unregistered caller must fail at
    boot/test time, never fall back to a silent default."""
    with pytest.raises(KeyError):
        oc.max_tokens_for("no_such_caller")


def test_near_ceiling_fraction_sits_in_the_measured_gap():
    """Derivation pinned (2026-08-09, prod api_usage, 6,634 rows): every healthy
    caller's max completed output <= 86% of its cap (orchestrator 3517/4096); every
    caller later caught truncating passed >= 95% first. The threshold must stay
    strictly inside that gap — below it the arm cries wolf on healthy traffic,
    above it the arm fires only after the margin is already gone."""
    assert 0.86 < oc.NEAR_CEILING_FRACTION < 0.95


# ── 2. the build gate — no new hardcoded ceilings ────────────────────────────────────────

def _py_files():
    for d in SCANNED_DIRS:
        yield from (REPO / d).rglob("*.py")


def _literal_max_tokens_sites():
    """Every hardcoded max_tokens number in the scanned trees, found by parsing:
      * `max_tokens=<number>` keyword on any call,
      * `"max_tokens": <number>` in any dict (raw-HTTP request bodies),
      * assignment to any name containing MAX_TOKENS with a numeric constant.
    Function-signature DEFAULTS (e.g. judge_transport's `max_tokens: int = 500`)
    are deliberately not flagged: in-repo callers pass registry values explicitly,
    and the default only serves external harnesses."""
    offenders = []
    for path in _py_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover
            continue
        rel = path.relative_to(REPO)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                for k in node.keywords:
                    if k.arg == "max_tokens" and isinstance(k.value, ast.Constant):
                        offenders.append(f"{rel}:{k.value.lineno}")
            elif isinstance(node, ast.Dict):
                for key, val in zip(node.keys, node.values):
                    if (isinstance(key, ast.Constant) and key.value == "max_tokens"
                            and isinstance(val, ast.Constant)):
                        offenders.append(f"{rel}:{key.lineno}")
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                value = node.value
                for t in targets:
                    name = getattr(t, "id", None) or getattr(t, "attr", None) or ""
                    if "MAX_TOKENS" in name and isinstance(value, ast.Constant):
                        offenders.append(f"{rel}:{node.lineno}")
    return offenders


def test_the_gate_scans_a_real_tree():
    """An AST walk that finds no files would pass the gate below while proving
    nothing (the vacuously-green failure mode this repo has hit before)."""
    assert sum(1 for _ in _py_files()) >= 50


def test_no_hardcoded_max_tokens_literals_at_call_sites():
    """THE GATE. A new `max_tokens=800` typed at a call site is a number that will
    rot silently on the next model change — exactly the postmortem/system_review
    failure. Register the caller in shared/output_ceilings.py (with evidence) and
    bind via max_tokens_for("<caller>") instead."""
    offenders = _literal_max_tokens_sites()
    assert not offenders, (
        "hardcoded max_tokens literal(s) found — move the number into "
        "shared/output_ceilings.py with its evidence and bind via max_tokens_for(): "
        + ", ".join(offenders))


def test_call_sites_bind_the_expected_registry_keys():
    """Spot-pin the caller-name wiring at the sites whose truncation caused real
    outages: the registry key at the site must be the api_usage caller tag, or the
    nightly margin check audits a different number than the code runs."""
    expects = {
        "agents/market_intelligence/postmortem.py": 'max_tokens_for("postmortem")',
        "agents/market_intelligence/system_review.py": 'max_tokens_for("system_review_weekly")',
        "agents/market_intelligence/catalyst_metrics_extractor.py":
            'max_tokens_for("catalyst_metrics_extractor")',
        "agents/market_intelligence/theme_engine.py": 'max_tokens_for("theme_advisor_discovery")',
        "core/context.py": 'max_tokens_for("context_compression")',
        "channels/telegram.py": 'max_tokens_for("healthcheck")',
    }
    for rel, needle in expects.items():
        src = (REPO / rel).read_text(encoding="utf-8")
        assert needle in src, f"{rel} no longer binds {needle}"


# ── 3. the detection arms ────────────────────────────────────────────────────────────────

def test_sweep_maps_a_changed_role_to_its_callers():
    """The boot recorder flags `callers_for_role(role)` when a role's model moves.
    THEME_ADVISOR_MODEL exercises the one-site/three-caller alias case."""
    assert oc.callers_for_role("THEME_ADVISOR_MODEL") == (
        "theme_advisor_assignment", "theme_advisor_discovery", "theme_advisor_split")
    assert oc.callers_for_role("POSTMORTEM_MODEL") == ("postmortem",)
    assert oc.callers_for_role("NO_SUCH_ROLE") == ()


def test_near_ceiling_arm_flags_the_margin_not_the_healthy():
    """Pure-logic check of cost_board._near_ceiling against the registry: a caller
    completing inside the last 10% of its cap is flagged with its margin; a healthy
    caller, a by-design ping, an unregistered caller, and a caller already reported
    by the truncation arm are all skipped."""
    from agents.market_intelligence.cost_board import _near_ceiling

    cap = oc.max_tokens_for("postmortem")
    rows = [
        {"caller": "postmortem", "max_completed": int(cap * 0.96)},        # tight
        {"caller": "catalyst_materiality", "max_completed": 68},           # healthy
        {"caller": "healthcheck", "max_completed": 5},                     # by design
        {"caller": "not_registered", "max_completed": 999999},             # no cap known
        {"caller": "theme_split", "max_completed": None},                  # no completions
        {"caller": "ep_grade_judge", "max_completed": 1499},               # already truncating
    ]
    tight = _near_ceiling(rows, already={"ep_grade_judge"})
    assert [x["caller"] for x in tight] == ["postmortem"]
    assert tight[0]["cap"] == cap
    assert tight[0]["pct_of_cap"] >= 90.0


def test_live_alarm_fires_on_truncation_and_respects_by_design(monkeypatch):
    """spend_tracker._maybe_alert_truncation: audit row on every truncated call,
    Telegram deduped per (caller, ET day), by-design pings never alert, and a
    failure inside the alarm never propagates into the spend-logging path."""
    import asyncio
    from unittest.mock import AsyncMock

    from agents.market_intelligence import spend_tracker as st

    audit = AsyncMock()
    tg = AsyncMock(return_value=True)
    import agents.market_intelligence.db as db_mod
    monkeypatch.setattr(db_mod, "log_audit_event", audit)
    import agents.market_intelligence.briefing as briefing_mod
    monkeypatch.setattr(briefing_mod, "send_telegram_message", tg)
    monkeypatch.setattr(st, "_TRUNCATION_TELEGRAMMED", {})

    asyncio.run(st._maybe_alert_truncation(
        caller="postmortem", model="claude-sonnet-5", output_tokens=1500))
    audit.assert_awaited_once()
    assert audit.await_args.args[0] == "llm_truncation_live"
    tg.assert_awaited_once()
    text = tg.await_args.args[0]
    assert "postmortem" in text and "1500" in text

    # same caller, same day → audit again, but NO second Telegram
    asyncio.run(st._maybe_alert_truncation(
        caller="postmortem", model="claude-sonnet-5", output_tokens=1500))
    assert audit.await_count == 2
    assert tg.await_count == 1

    # by-design ping → neither
    asyncio.run(st._maybe_alert_truncation(
        caller="healthcheck", model="claude-haiku-4-5-20251001", output_tokens=5))
    assert audit.await_count == 2 and tg.await_count == 1

    # an exploding audit path must not raise into the caller
    async def boom(*a, **k):
        raise RuntimeError("audit down")
    monkeypatch.setattr(db_mod, "log_audit_event", boom)
    asyncio.run(st._maybe_alert_truncation(
        caller="theme_split", model="claude-sonnet-5", output_tokens=1750))  # no raise


def test_tracker_hooks_the_alarm_on_both_providers():
    """Both INSERT paths (Anthropic + Perplexity-normalised) must feed the live
    alarm — the cheaper Perplexity path must not become the blind spot again."""
    src = (REPO / "agents/market_intelligence/spend_tracker.py").read_text(encoding="utf-8")
    assert src.count("_maybe_alert_truncation(") >= 3  # def + 2 call sites
    anth = src.split("async def log_anthropic_call(")[1].split("async def ")[0]
    pplx = src.split("async def log_perplexity_call(")[1]
    assert "_maybe_alert_truncation(" in anth
    assert "_maybe_alert_truncation(" in pplx
