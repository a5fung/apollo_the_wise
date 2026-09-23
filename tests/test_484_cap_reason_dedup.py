"""#484 — the cap-block reason strings must have exactly ONE source.

Operator-ruled 2026-07-27 (the /simplify flag raised 7/18, deliberately not
auto-applied because it sits on the money path behind the #461 cap lock).

WHY THIS IS A TEST AND NOT JUST A REFACTOR: these strings are CONSUMED BY STRING
MATCH, not merely displayed. The #197 CAP+1 alert and the ledger's `cap_blocked`
mapping both key off the exact format. They were hand-copied into two call sites —
`live_tracker._check_safeguards` (the cheap STEP-2 early gate) and
`entry_pipeline.submit_trade_entry` STEP-6 (the authoritative recount under the
per-mode lock). Editing one copy alone would silently break the alert with nothing
failing loudly, which is precisely the failure mode a test can prevent and a
refactor alone cannot.

`count_open_positions` had already been deduped for this reason; only the reason
BUILDING hadn't. The per-STRATEGY pair was found duplicated the same way while
fixing the global one — same class, same risk, both folded here.
"""
from __future__ import annotations

import re
from pathlib import Path

from agents.market_intelligence.broker.skip_reasons import (
    BLOCK_MAX_POSITIONS,
    BLOCK_STRATEGY_POSITION_CAP,
    cap_block_reason,
    strategy_cap_block_reason,
)

_BROKER = Path(__file__).resolve().parents[1] / "agents" / "market_intelligence" / "broker"
_CALL_SITES = ("live_tracker.py", "entry_pipeline.py")


def test_global_cap_reason_format_is_unchanged():
    """Byte-identical to the hand-copied string it replaced. If this changes, the
    #197 CAP+1 alert stops matching — so the format is the contract, not a detail."""
    assert cap_block_reason(5, 5, "live") == "block:max_positions: 5/5 (mode=live)"
    assert cap_block_reason(3, 5, "paper") == "block:max_positions: 3/5 (mode=paper)"
    assert cap_block_reason(5, 5, "live").startswith(BLOCK_MAX_POSITIONS)


def test_strategy_cap_reason_format_is_unchanged():
    assert strategy_cap_block_reason("magna53", 2, 2, "live") == (
        "block:strategy_position_cap: magna53 2/2 (mode=live)"
    )
    assert strategy_cap_block_reason("magna53", 2, 2, "live").startswith(
        BLOCK_STRATEGY_POSITION_CAP
    )


def test_no_call_site_hand_builds_a_cap_reason_anymore():
    """THE point of #484. A hand-built f-string at either call site is the
    desync risk returning — fail loudly rather than let it drift back."""
    pattern = re.compile(
        r'f"\{BLOCK_(MAX_POSITIONS|STRATEGY_POSITION_CAP)\}:'
    )
    offenders = []
    for name in _CALL_SITES:
        src = (_BROKER / name).read_text()
        for i, line in enumerate(src.splitlines(), 1):
            if pattern.search(line):
                offenders.append(f"{name}:{i}: {line.strip()}")
    assert not offenders, (
        "a cap-block reason is being hand-built again instead of using "
        "skip_reasons.cap_block_reason / strategy_cap_block_reason:\n  "
        + "\n  ".join(offenders)
        + "\nThese strings are string-MATCHED by the #197 CAP+1 alert; two copies "
          "can desync silently."
    )


def test_both_call_sites_actually_use_the_helpers():
    """Complement to the negative test above: prove the helpers are wired in, so
    the previous test can't pass merely because someone deleted the logic."""
    for name in _CALL_SITES:
        src = (_BROKER / name).read_text()
        assert "cap_block_reason(" in src, f"{name} no longer calls cap_block_reason"
        assert "strategy_cap_block_reason(" in src, (
            f"{name} no longer calls strategy_cap_block_reason"
        )
