"""The ORB submission window is now a rule-set field — and its default must not move.

2026-09-06. `window:out_of_orb` is our largest single skip class (11 fires in 30 days, 29 in
90), and its outcome was previously unmeasurable: the replay harness enforced the same 09:45
cut-off it was supposed to test, so every one of those names came back `no_trade`. The existing
`mi_orb_extension_shadow` cannot answer it either — that shadow is fed from orders we ALREADY
placed, and a name skipped at the window never gets an order.

Making the window a field lets it be counterfactualled. The risk that comes with that is
silently moving the LIVE default, so that is what these pin.
"""
from datetime import time

from scripts.ep_replay import RULESETS


def test_every_era_ruleset_keeps_the_live_0945_window():
    """CLAUDE.md: HIGHs at 09:45-09:59 -> WINDOW_OUT_OF_ORB. Era sets must be untouched."""
    for name in ("era_a", "era_b", "era_c", "current"):
        assert RULESETS[name].submit_window_end == time(9, 45), \
            f"{name} no longer uses the live 09:45 submission window"


def test_the_variant_differs_in_exactly_one_field():
    """A counterfactual that changes two things answers neither question."""
    base, var = RULESETS["era_c"], RULESETS["era_c_late_window"]
    differing = [f for f in base.__dataclass_fields__
                 if getattr(base, f) != getattr(var, f)]
    assert differing == ["name", "submit_window_end"], \
        f"the late-window variant also changes {differing}"
    assert var.submit_window_end == time(10, 0)


def test_the_gate_reads_the_ruleset_not_a_literal():
    """The whole point: a hardcoded 09:45 makes the question unanswerable."""
    import inspect
    import scripts.ep_replay as er
    src = inspect.getsource(er.walk_campaign) if hasattr(er, "walk_campaign") else ""
    if not src:  # the gate lives in the module-level walk; fall back to file text
        with open("scripts/ep_replay.py", encoding="utf-8") as fh:
            src = fh.read()
    assert "submit >= rs.submit_window_end" in src, \
        "the window gate must read the rule-set"
    assert "submit >= time(9, 45)" not in src, \
        "the hardcoded window literal is back — the counterfactual is dead again"
