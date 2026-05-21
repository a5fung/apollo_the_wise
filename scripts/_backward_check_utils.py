"""Shared helpers for backward-check scripts (#59, 2026-05-21).

Two methodology hygiene rules apply to every backward-check script:

  1. ETF filter: only CS/ADRC tickers in the cohort. Pre-P2.0b-fix
     legacy ETF alerts (USAX, USGG 4/20-class) pollute outcome
     analysis with leveraged-product returns. Cohort SQL must JOIN
     mi_security_types and exclude non-stock entries.

  2. Median + IQR alongside avg. Single-trade outliers (AXTI +47%,
     KOD +14.7% × 6 duplicates) can flip band-level conclusions on
     small N. Report all three so the operator can see distributional
     shape, not just mean which gets dragged by outliers.

Use these helpers in any new backward-check script. Add the ETF filter
predicate to your SQL; use `band_stats()` + `format_band_row()` for
band-level reporting.

Filed as task #59 after user caught ETF pollution in #53 + AXTI outlier
dominance in low-ratio band conclusion.
"""
from __future__ import annotations

import statistics
from typing import Iterable


# SQL fragment to JOIN against mi_security_types and exclude non-stock.
# Apply via:
#   FROM mi_ep_alerts a
#   LEFT JOIN mi_security_types st ON st.ticker = a.ticker
#   WHERE ... AND {SECURITY_TYPE_FILTER_CLAUSE}
SECURITY_TYPE_FILTER_CLAUSE = (
    "(st.security_type IS NULL OR st.security_type IN ('CS', 'ADRC'))"
)


def band_stats(returns: Iterable[float | None]) -> dict:
    """Compute n, avg, median, p25, p75, win rates (>=+5%, >=+10%) for a
    list of forward returns. Skips None entries.

    Returns dict with keys: n, n_with_return, avg, median, p25, p75,
    winners5, winners5_pct, winners10, winners10_pct, range_str.

    range_str is a human-readable summary of the distribution shape
    (e.g. "median 5.2% [IQR -2.1 to 12.3]") for use in table cells.
    """
    items = [r for r in returns if r is not None]
    n_with_return = len(items)
    if n_with_return == 0:
        return {
            "n": 0,
            "n_with_return": 0,
            "avg": None,
            "median": None,
            "p25": None,
            "p75": None,
            "winners5": 0,
            "winners5_pct": None,
            "winners10": 0,
            "winners10_pct": None,
            "range_str": "—",
        }
    sorted_items = sorted(items)
    n = len(sorted_items)
    avg = sum(sorted_items) / n
    median = statistics.median(sorted_items)
    p25 = sorted_items[max(0, n // 4 - 1)] if n >= 4 else sorted_items[0]
    p75 = sorted_items[min(n - 1, (3 * n) // 4)] if n >= 4 else sorted_items[-1]
    winners5 = sum(1 for r in items if r >= 5)
    winners10 = sum(1 for r in items if r >= 10)
    winners5_pct = winners5 / n * 100
    winners10_pct = winners10 / n * 100
    range_str = f"med {median:+.1f}% [{p25:+.1f} to {p75:+.1f}]"
    return {
        "n": n,
        "n_with_return": n_with_return,
        "avg": avg,
        "median": median,
        "p25": p25,
        "p75": p75,
        "winners5": winners5,
        "winners5_pct": winners5_pct,
        "winners10": winners10,
        "winners10_pct": winners10_pct,
        "range_str": range_str,
    }


def format_band_row(
    label: str,
    total_n: int,
    cohort_total_n: int,
    stats: dict,
    label_width: int = 55,
) -> str:
    """Format a single band row for backward-check output table.

    Columns: label, N, %, avg, median+IQR, winners ≥+5%, winners ≥+10%

    Use the same format across all backward-check scripts for visual
    consistency.
    """
    pct = total_n / cohort_total_n * 100 if cohort_total_n > 0 else 0
    avg_str = f"{stats['avg']:+.2f}%" if stats["avg"] is not None else "—"
    if stats["n_with_return"]:
        w5_str = f"{stats['winners5']}/{stats['n_with_return']} ({stats['winners5_pct']:.0f}%)"
        w10_str = f"{stats['winners10']}/{stats['n_with_return']} ({stats['winners10_pct']:.0f}%)"
    else:
        w5_str = "no outcomes"
        w10_str = "—"
    return (
        f"{label:<{label_width}} {total_n:<5} {pct:>4.1f}% "
        f"{avg_str:<10} {stats['range_str']:<26} "
        f"{w5_str:<14} {w10_str:<14}"
    )


def format_header(label_width: int = 55) -> str:
    """Standard header row for band-level tables."""
    return (
        f"{'BAND':<{label_width}} {'N':<5} {'%':<6} "
        f"{'avg_5d':<10} {'median + IQR':<26} "
        f"{'winners ≥+5%':<14} {'≥+10%':<14}"
    )
