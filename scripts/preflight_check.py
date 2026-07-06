"""
Post-deploy preflight check — walks every enabled non-shadow strategy through
the safeguard layer to confirm the entry pipeline can authenticate and query
its mode-specific Alpaca account.

Usage (run after every deploy):

    docker exec apollo-market python -m scripts.preflight_check

Exits non-zero if ANY strategy raises while exercising:
  - resolve_account_mode_for_strategy (catches phase/mode mismatch)
  - alpaca.get_account(account_mode) (catches missing/wrong creds at the
    same call site that fires during a real ORB entry — this is the path
    that broke on 2026-05-13 with 'ALPACA_LIVE_API_KEY' KeyError).
  - _check_safeguards full pass (max positions, per-strategy cap, daily
    loss, drawdown breaker)

Why this specifically: boot-time `verify_dual_account_clients()` only checks
clients we know to instantiate. It doesn't exercise the strategy-driven
code path. Today's outage proved boot ≠ runtime — env vars can be present
for one mode and missing for the mode a strategy actually routes to.

Designed to run as the LAST step of every deploy, before declaring it green.
"""
from __future__ import annotations

import asyncio
import logging
import sys

from agents.market_intelligence.agent import _bootstrap_alpaca_credentials
from agents.market_intelligence.broker.live_tracker import _check_safeguards
from agents.market_intelligence.constants import resolve_account_mode_for_strategy
from agents.market_intelligence.strategies.registry import load_strategies

# Skip-reason prefixes that count as PASS even when (ok=False) — these are
# real safeguards firing as designed (e.g. drawdown breaker tripped). They
# do block real entries, but their firing is *correct*. Anything else
# (setup:* infra:*) is an infra failure and fails preflight.
_BENIGN_BLOCK_PREFIXES = ("block:",)

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("preflight")
logger.setLevel(logging.INFO)


async def main() -> int:
    # Bootstrap Alpaca credentials EXACTLY like agent.py does at container
    # boot. Without this, the legacy ALPACA_API_KEY → ALPACA_PAPER_* remap
    # never fires in this subprocess and we'd false-alarm on a healthy
    # container that just hasn't migrated env var names yet.
    try:
        _bootstrap_alpaca_credentials()
    except Exception as e:
        print(f"PREFLIGHT FAILED — bootstrap raised: {e}")
        return 1

    strategies = await load_strategies()
    print("\n=== Preflight: entry-pipeline safeguard walk ===\n")

    failures: list[tuple[str, str, str]] = []
    skipped: list[str] = []
    ok_rows: list[tuple[str, str, str]] = []

    for sid, s in sorted(strategies.items()):
        if not s.enabled:
            skipped.append(f"  {sid:20s}  disabled")
            continue
        if s.phase in ("shadow", "deprecated"):
            # deprecated (#424, 2026-07-06): terminal — never submits (the entry
            # gate blocks it before resolve_account_mode is ever called; resolve
            # itself raises for 'deprecated' as defense-in-depth). Skip it here
            # exactly like shadow, else the preflight crashes walking a strategy
            # that can never fire a real entry (market-agent boot 7/6 sibling of
            # the CHECK-constraint miss — a new phase value must be handled on
            # EVERY path that switches on phase).
            _label = "deprecated (retired, no submit)" if s.phase == "deprecated" else "shadow phase (no live submit)"
            skipped.append(f"  {sid:20s}  {_label}")
            continue

        try:
            mode = resolve_account_mode_for_strategy(s)
        except Exception as e:
            failures.append((sid, "?", f"resolve_account_mode raised: {e}"))
            continue

        try:
            # 2026-05-18: _check_safeguards returns 3-tuple (ok, reason, multiplier)
            # post-tiered-drawdown redesign. Preflight only uses ok+reason.
            ok, reason, _multiplier = await _check_safeguards(
                account_mode=mode, signal_type=s.signal_type,
            )
        except Exception as e:
            failures.append((sid, mode, f"_check_safeguards raised: {e}"))
            continue

        if ok:
            ok_rows.append((sid, mode, "PASS"))
        elif reason and reason.startswith(_BENIGN_BLOCK_PREFIXES):
            # Real safeguard fired — that's correct behavior, not preflight fail.
            ok_rows.append((sid, mode, f"BLOCKED-OK ({reason})"))
        else:
            # setup:* / infra:* / anything non-block:* = infra failure
            failures.append((sid, mode, f"{reason}"))

    # Print report
    for line in skipped:
        print(line)
    for sid, mode, verdict in ok_rows:
        marker = "✓"
        print(f"  {marker} {sid:20s}  mode={mode:5s}  {verdict}")
    for sid, mode, err in failures:
        print(f"  ✗ {sid:20s}  mode={mode:5s}  FAILED: {err}")

    print()
    if failures:
        print(f"PREFLIGHT FAILED — {len(failures)} strategy/mode pair(s) blocked by infra.")
        print("Resolve before declaring the deploy green. This is the same")
        print("safeguard path that fires on every real ORB entry.")
        return 1

    print(f"PREFLIGHT OK — {len(ok_rows)} strategy/mode pair(s) verified, "
          f"{len(skipped)} skipped.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
