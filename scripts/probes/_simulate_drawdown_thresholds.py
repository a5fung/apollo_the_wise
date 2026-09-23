"""Retroactive simulation of drawdown breaker trip/release timelines for
candidate thresholds against existing `mi_account_equity_snapshots`.

For each candidate trip threshold, walks paper account equity history
chronologically through the asymmetric-hysteresis state machine
(trip at -trip%, release at -trip/2%). Outputs:
  - Trip events with date + drawdown %
  - Release events with date + recovery %
  - Time-in-tripped (days)
  - Trip rate (per-quarter equivalent)

Preview only — final calibration happens once 14+ days of snapshots
accumulate (~2026-05-27).

Run: docker exec apollo-market python -m scripts._simulate_drawdown_thresholds
"""
from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import date

from agents.market_intelligence.db import get_pool


# Candidate trip thresholds (as positive percentages — e.g. 5.0 = -5% drawdown)
CANDIDATES = [5.0, 7.0, 8.0, 10.0]


def simulate_threshold(snapshots: list[tuple[date, float]], trip_pct: float) -> dict:
    """Walk snapshots chronologically applying the breaker state machine.

    Returns dict with trips, releases, time_in_tripped_days, etc.
    """
    release_pct = trip_pct / 2.0  # asymmetric hysteresis

    state = "OK"
    peak = snapshots[0][1]
    transitions = []  # list of (date, event_type, drawdown_pct, equity, peak)
    days_tripped = 0
    prev_state = "OK"

    for (snap_date, equity) in snapshots:
        if state == "OK":
            # Update peak only when not tripped
            if equity > peak:
                peak = equity
            drawdown_pct = (equity - peak) / peak * 100.0
            if drawdown_pct <= -trip_pct:
                state = "TRIPPED"
                transitions.append((snap_date, "TRIPPED", drawdown_pct, equity, peak))
        else:  # TRIPPED
            drawdown_pct = (equity - peak) / peak * 100.0
            if drawdown_pct >= -release_pct:
                state = "OK"
                # Reset peak to current equity on release per safeguards.md
                peak = equity
                transitions.append((snap_date, "RELEASED", drawdown_pct, equity, equity))
        if state == "TRIPPED":
            days_tripped += 1

    n_trips = sum(1 for t in transitions if t[1] == "TRIPPED")
    n_releases = sum(1 for t in transitions if t[1] == "RELEASED")
    n_days = len(snapshots)
    # Trip rate scaled to quarterly equivalent (~63 trading days per quarter)
    trips_per_quarter = (n_trips / max(n_days, 1)) * 63

    return {
        "trip_pct": trip_pct,
        "release_pct": release_pct,
        "n_trips": n_trips,
        "n_releases": n_releases,
        "current_state": state,
        "days_tripped": days_tripped,
        "n_days_observed": n_days,
        "trips_per_quarter_est": trips_per_quarter,
        "transitions": transitions,
    }


async def main():
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT snapshot_date, equity
            FROM mi_account_equity_snapshots
            WHERE account_mode = 'paper'
            ORDER BY snapshot_date
        """)

    if not rows:
        print("No equity snapshots found.")
        return

    snapshots = [(r["snapshot_date"], float(r["equity"])) for r in rows]
    print(f"Loaded {len(snapshots)} paper-account equity snapshots")
    print(f"Range: {snapshots[0][0]} → {snapshots[-1][0]}")
    print(f"Equity: ${snapshots[0][1]:,.2f} → ${snapshots[-1][1]:,.2f}")
    print()

    # Print snapshot history for context
    print("Snapshot history:")
    print(f"  {'date':<12} {'equity':>12} {'drawdown vs peak':>18}")
    running_peak = snapshots[0][1]
    for d, eq in snapshots:
        running_peak = max(running_peak, eq)
        dd = (eq - running_peak) / running_peak * 100.0
        print(f"  {str(d):<12} ${eq:>11,.2f} {dd:+18.2f}%")
    print()

    print("=" * 72)
    print("CANDIDATE THRESHOLD SIMULATION RESULTS")
    print("=" * 72)
    print(f"{'trip%':>6} {'rel%':>5} {'trips':>5} {'rels':>4} {'days_tripped':>13} "
          f"{'state':>9} {'trips/qtr':>11}")
    print("-" * 72)
    results = []
    for cand in CANDIDATES:
        r = simulate_threshold(snapshots, cand)
        results.append(r)
        print(f"{r['trip_pct']:>5.1f}% {r['release_pct']:>4.1f}% "
              f"{r['n_trips']:>5} {r['n_releases']:>4} "
              f"{r['days_tripped']:>13} "
              f"{r['current_state']:>9} "
              f"{r['trips_per_quarter_est']:>11.1f}")

    print()
    print("Per-threshold transition timelines:")
    for r in results:
        if not r["transitions"]:
            print(f"  trip={r['trip_pct']}%: no transitions in window")
            continue
        print(f"  trip={r['trip_pct']}%:")
        for (td, evt, dd_pct, equity, peak) in r["transitions"]:
            print(f"    {td} {evt:<8} drawdown={dd_pct:+6.2f}% "
                  f"equity=${equity:,.2f} peak=${peak:,.2f}")

    print()
    print("Acceptance gate target: trips/quarter <= ~1.0 (from review)")
    cleanest = min(results, key=lambda r: abs(r["trips_per_quarter_est"] - 1.0))
    print(f"Closest-to-target threshold (this window): trip={cleanest['trip_pct']}% "
          f"(estimated {cleanest['trips_per_quarter_est']:.1f} trips/quarter)")


if __name__ == "__main__":
    asyncio.run(main())
