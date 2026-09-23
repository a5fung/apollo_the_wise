#!/usr/bin/env python3
"""#454 part 3 — drawdown-breaker LIVE-path exercise (#151-style).

WHY: the tiered drawdown breaker is the -12% backstop every accepted risk in the
v1.0 premortem leans on, and it has only ever fired on PAPER. The live-mode
*snapshot + compute* half runs daily (mi_safeguard_state carries a live row), but
no live tier TRANSITION has ever occurred, so the live ENFORCEMENT path -
_check_safeguards consuming a non-OK tier, and the sizing site applying it - has
never executed.

WHAT THIS IS NOT: this cannot make the breaker fire live for real. That stays
event-gated on a genuine -12% drawdown. This closes the "never EXECUTED live"
gap, not the "never FIRED live" gap.

SAFETY (the design constraint):
  * ZERO WRITES. Nothing here mutates mi_safeguard_state, mi_account_equity_
    snapshots, or any trade state. The only injection is an in-process patch of
    read_breaker_state for the duration of a call; the process exits and residue
    is impossible by construction.
  * The rejected alternative was setting the live safeguard row to each tier and
    restoring it. REDUCE returns ok=True with a 0.5x multiplier, so a crash
    mid-exercise would leave Monday's live entries SILENTLY half-sized, with the
    16:12 ET cron not recomputing until after the 9:31 entry window. That is a
    silent strategy alteration on the money path.
  * Synthetic equity snapshots were likewise rejected: a stray high-equity row
    raises the 30-day rolling peak and mis-computes every later drawdown -> a
    false BLOCK days later with no obvious cause.
  * Everything EXCEPT the breaker state stays real - real Alpaca auth, real
    position count, real daily-loss check. The breaker gate is last in
    _check_safeguards, so reaching it means all prior gates genuinely passed.

RUN (inside the container that owns the money path):
    docker exec -i apollo-execution python - < scripts/_454_drawdown_live_path_exercise.py
"""
from __future__ import annotations

import asyncio
import contextlib

MODE = "live"
FAILURES: list[str] = []
CHECKS = 0


def check(label: str, actual, expected) -> None:
    global CHECKS
    CHECKS += 1
    ok = actual == expected
    print(f"  {'PASS' if ok else 'FAIL'}  {label}")
    if not ok:
        print(f"        expected {expected!r}")
        print(f"        actual   {actual!r}")
        FAILURES.append(label)


@contextlib.contextmanager
def injected_tier(tier: str):
    """Patch read_breaker_state at its module of origin.

    live_tracker imports it INSIDE _check_safeguards, so the lookup happens at
    call time against the drawdown_breaker module - patching the attribute there
    is what the production code actually resolves.
    """
    from agents.market_intelligence.broker import drawdown_breaker as db_mod
    original = db_mod.read_breaker_state

    async def _fake(mode: str) -> str:
        assert mode == MODE, f"expected mode={MODE}, got {mode}"
        return tier

    db_mod.read_breaker_state = _fake
    try:
        yield
    finally:
        db_mod.read_breaker_state = original


async def main() -> None:
    from agents.market_intelligence.constants import DRAWDOWN_BREAKER_PHASE
    from agents.market_intelligence.broker.drawdown_breaker import (
        _STATE_BLOCK, _STATE_OK, _STATE_REDUCE, _STATE_WATCH,
        _LEGACY_STATE_TRIPPED, _next_state, get_tier_multiplier,
        read_breaker_state,
    )
    from agents.market_intelligence.broker.entry_pipeline import _apply_composite_multiplier
    from agents.market_intelligence.broker.live_tracker import _check_safeguards
    from agents.market_intelligence.broker.skip_reasons import BLOCK_DRAWDOWN_BREAKER

    print("=" * 72)
    print("#454 part 3 — drawdown-breaker LIVE-path exercise")
    print("=" * 72)

    # ── Precondition: the enforcement block is gated on this constant ───────
    print("\n[0] PRECONDITION — enforcement must be active")
    check("DRAWDOWN_BREAKER_PHASE == 'active'", DRAWDOWN_BREAKER_PHASE, "active")
    if DRAWDOWN_BREAKER_PHASE != "active":
        print("\n*** enforcement inert — the rest proves nothing about production ***")
        return

    live_state_before = await read_breaker_state(MODE)
    print(f"      live breaker state (read-only, untouched): {live_state_before!r}")

    # ── Part A: transition matrix (pure, zero writes) ───────────────────────
    # Bands per docs/setups/safeguards.md: WATCH -4/-2.5, REDUCE -7/-4, BLOCK -12/-7.
    print("\n[A] TRANSITION MATRIX — _next_state, pure function")
    # Trip side: jump straight to the deepest applicable tier in one snapshot.
    check("OK     @ -0.5% -> OK",     _next_state(_STATE_OK, -0.005), _STATE_OK)
    check("OK     @ -4%   -> WATCH",  _next_state(_STATE_OK, -0.040), _STATE_WATCH)
    check("OK     @ -7%   -> REDUCE", _next_state(_STATE_OK, -0.070), _STATE_REDUCE)
    check("OK     @ -12%  -> BLOCK",  _next_state(_STATE_OK, -0.120), _STATE_BLOCK)
    check("OK     @ -30%  -> BLOCK",  _next_state(_STATE_OK, -0.300), _STATE_BLOCK)
    # Release side: step up ONE tier per evaluation, each gated on its own band.
    # NOTE the release threshold is the level equity must RECOVER TO, not a
    # depth you fall past: at -8% a BLOCK has not yet reached -7%, so it holds.
    # (Both -8%/-5% cases below were wrong in the first draft of this harness;
    # corrected against _next_state:118-132 + safeguards.md, code was right.)
    check("BLOCK  @ -8%   holds (not yet >= -7%)", _next_state(_STATE_BLOCK, -0.080), _STATE_BLOCK)
    check("BLOCK  @ -6%   -> REDUCE (recovered)",  _next_state(_STATE_BLOCK, -0.060), _STATE_REDUCE)
    check("BLOCK  @ -11%  stays",     _next_state(_STATE_BLOCK, -0.110), _STATE_BLOCK)
    check("REDUCE @ -5%   holds (not yet >= -4%)", _next_state(_STATE_REDUCE, -0.050), _STATE_REDUCE)
    check("REDUCE @ -3%   -> WATCH (recovered)",   _next_state(_STATE_REDUCE, -0.030), _STATE_WATCH)
    check("REDUCE @ -6.9% stays",     _next_state(_STATE_REDUCE, -0.069), _STATE_REDUCE)
    check("WATCH  @ -2%   -> OK",     _next_state(_STATE_WATCH, -0.020), _STATE_OK)
    check("WATCH  @ -3.9% stays",     _next_state(_STATE_WATCH, -0.039), _STATE_WATCH)
    # One evaluation releases at most ONE tier, even on a full recovery.
    check("BLOCK  @ 0%    -> REDUCE only (one step)", _next_state(_STATE_BLOCK, 0.0), _STATE_REDUCE)
    # Hysteresis: a value inside the dead band must NOT flap either way.
    check("OK     @ -3%   stays OK",  _next_state(_STATE_OK, -0.030), _STATE_OK)
    check("WATCH  @ -3%   stays",     _next_state(_STATE_WATCH, -0.030), _STATE_WATCH)
    # Legacy binary state string must still resolve (pre-2026-05-18 rows).
    print(f"      legacy {_LEGACY_STATE_TRIPPED!r} @ -1% -> "
          f"{_next_state(_LEGACY_STATE_TRIPPED, -0.010)!r} (no crash)")

    # ── Part B: multipliers ─────────────────────────────────────────────────
    print("\n[B] TIER MULTIPLIERS — get_tier_multiplier")
    check("OK     -> 1.0", get_tier_multiplier(_STATE_OK), 1.0)
    check("WATCH  -> 1.0", get_tier_multiplier(_STATE_WATCH), 1.0)
    check("REDUCE -> 0.5", get_tier_multiplier(_STATE_REDUCE), 0.5)
    check("BLOCK  -> 0.0", get_tier_multiplier(_STATE_BLOCK), 0.0)

    # ── Part C: THE LIVE ENFORCEMENT PATH (the never-executed branch) ───────
    print(f"\n[C] LIVE ENFORCEMENT — real _check_safeguards(account_mode={MODE!r}),"
          f" breaker state injected")
    print("     (auth / halt / position-cap / daily-loss all REAL; breaker gate is last)")

    with injected_tier(_STATE_OK):
        ok, reason, mult = await _check_safeguards(account_mode=MODE)
        print(f"      OK     -> ok={ok} reason={reason!r} mult={mult}")
        check("OK: passes with 1.0x", (ok, mult), (True, 1.0))

    with injected_tier(_STATE_WATCH):
        ok, reason, mult = await _check_safeguards(account_mode=MODE)
        print(f"      WATCH  -> ok={ok} reason={reason!r} mult={mult}")
        check("WATCH: passes with 1.0x", (ok, mult), (True, 1.0))

    with injected_tier(_STATE_REDUCE):
        ok, reason, mult = await _check_safeguards(account_mode=MODE)
        print(f"      REDUCE -> ok={ok} reason={reason!r} mult={mult}")
        check("REDUCE: passes with 0.5x", (ok, mult), (True, 0.5))

    with injected_tier(_STATE_BLOCK):
        ok, reason, mult = await _check_safeguards(account_mode=MODE)
        print(f"      BLOCK  -> ok={ok} reason={reason!r} mult={mult}")
        check("BLOCK: hard-blocks at 0.0x", (ok, mult), (False, 0.0))
        check("BLOCK: carries the drawdown skip-reason",
              reason.startswith(BLOCK_DRAWDOWN_BREAKER), True)

    # ── Part D: the multiplier is actually APPLIED to share count ───────────
    # safeguards.md: final_shares = floor(shares x strategy_mult x drawdown_mult)
    print("\n[D] SIZING APPLICATION — _apply_composite_multiplier")
    check("100 sh @ REDUCE(0.5x)            -> 50", _apply_composite_multiplier(100, 0.5), (50, False))
    check("100 sh @ REDUCE x 9M-Day2 0.25x  -> 25", _apply_composite_multiplier(100, 0.25), (25, False))
    check("odd lot 7 sh @ 0.5x floors to 3",        _apply_composite_multiplier(7, 0.5), (3, False))
    check("1 sh @ 0.5x floors to 0 (caller skips)", _apply_composite_multiplier(1, 0.5), (0, False))
    check("RED-3 clamp: >1.0x never sizes past baseline",
          _apply_composite_multiplier(100, 1.5), (100, True))

    # ── Part E: the second consumer of the same surface ─────────────────────
    print("\n[E] SECOND CONSUMER — intraday_drawdown suppression vs persisted tier")
    from agents.market_intelligence.broker.intraday_drawdown import (
        _persisted_depth, _deepest_crossed_tier,
    )
    check("-4% crosses WATCH",   _deepest_crossed_tier(-0.040), _STATE_WATCH)
    check("-7% crosses REDUCE",  _deepest_crossed_tier(-0.070), _STATE_REDUCE)
    check("-1% crosses nothing", _deepest_crossed_tier(-0.010), None)
    # DELIBERATE asymmetry vs the breaker, not a bug: this alerter's Stage-1
    # vocabulary is WATCH/REDUCE only (see its docstring) — a BLOCK-depth
    # drawdown reports REDUCE and the alert body carries the raw dd%. The
    # ENFORCEMENT tier is the breaker's, exercised in [C] above.
    check("-12% reports REDUCE (Stage-1 vocabulary, by design)",
          _deepest_crossed_tier(-0.120), _STATE_REDUCE)
    check("persisted BLOCK outranks an intraday WATCH crossing",
          _persisted_depth(_STATE_BLOCK) >= _persisted_depth(_STATE_WATCH), True)

    # ── Residue check ──────────────────────────────────────────────────────
    print("\n[F] RESIDUE — live breaker state must be untouched")
    live_state_after = await read_breaker_state(MODE)
    check("live state unchanged", live_state_after, live_state_before)
    print(f"      before={live_state_before!r} after={live_state_after!r}")

    print("\n" + "=" * 72)
    if FAILURES:
        print(f"RESULT: {len(FAILURES)} FAILED of {CHECKS} — {FAILURES}")
    else:
        print(f"RESULT: ALL {CHECKS} CHECKS PASSED — live enforcement path executed clean")
    print("NOTE: a genuine live FIRE stays event-gated on a real -12% drawdown.")
    print("=" * 72)


asyncio.run(main())
