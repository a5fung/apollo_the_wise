"""Shared SQL fragments for the W3 judge-review surfaces (#244 / ADR 0011).

The 5d Maximum Favorable Excursion (MFE) "did this name run after alert_date?" join is
identical across judge_delta_review.py and unjustified_demotion_sweep.py (and mirrors the
LATERAL in missed_outcomes.py:341). Defined ONCE here so the MFE definition — bar count,
open-vs-prevclose basis — can't drift between the two review tools.

Contract: the consuming query MUST expose a base cohort CTE aliased `d` with `d.ticker` and
`d.alert_date`. `_MFE_JOINS` adds `d0` (alert-day open) + `h5` (max high over 6 bars from
alert_date inclusive); `_MFE_EXPR` is the resulting fraction (NULL when prices missing).
"""

# Two LATERAL joins onto a base cohort CTE aliased `d`.
_MFE_JOINS = """
    LEFT JOIN LATERAL (
        SELECT open_price FROM mi_daily_closes
        WHERE ticker = d.ticker AND trade_date = d.alert_date
    ) d0 ON TRUE
    LEFT JOIN LATERAL (
        SELECT MAX(high_price) AS h FROM (
            SELECT high_price FROM mi_daily_closes
            WHERE ticker = d.ticker AND trade_date >= d.alert_date
            ORDER BY trade_date ASC LIMIT 6
        ) x
    ) h5 ON TRUE
"""

# 5d MFE as a fraction off the alert-day open (regime-independent; NULL when prices absent).
_MFE_EXPR = """
    CASE WHEN d0.open_price > 0 AND h5.h IS NOT NULL
         THEN (h5.h - d0.open_price) / d0.open_price END AS mfe_5d
"""
