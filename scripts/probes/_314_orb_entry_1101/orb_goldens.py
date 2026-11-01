#!/usr/bin/env python3
"""#314 ORB-entry replay — the synthetic dry run (docs/analysis/parabolic_short_orb_entry_prereg_2026-11-01.md §8).

Fourteen hand-built fixtures (eleven in the first draft; #9b, #12 and #13 added at the 11-01 review, their hand numbers written before the
stop rule was changed in the code), each a few minute bars per session, with the HAND numbers of the registration written here as constants
BEFORE the walk code ran on them. `orb_replay.py --dry-run` walks every fixture through the same `walk_episode` the real run uses and
refuses on any number off by more than 1e-9. Nothing here reads a real bar; the fixture dates are inside the seal and are not early
closes.

Bars are (ts, open, high, low, close). Sessions S1 = D0+1, S2 = D0+2, S3 = D0+3 (D0 is never walked).
"""
from __future__ import annotations

S1, S2, S3 = "2023-07-05", "2023-07-06", "2023-07-07"
SESSIONS = (S1, S2, S3)
TOL = 1e-9

# ---- the base winning series (#1), reused by #5, #6, #7, #8 and #10 -------------------------------------------------------------------
WIN_S1 = [("09:30", 10.00, 10.50, 9.80, 10.20), ("09:31", 10.20, 10.60, 10.10, 10.40), ("09:32", 10.40, 10.70, 10.30, 10.50),
          ("09:33", 10.50, 10.65, 10.35, 10.40), ("09:34", 10.40, 10.55, 10.20, 10.30), ("09:35", 10.30, 10.45, 10.00, 10.05),
          ("09:40", 10.05, 10.10, 9.70, 9.75), ("10:00", 9.75, 9.90, 9.40, 9.50), ("12:00", 9.50, 9.60, 9.00, 9.10),
          ("15:59", 9.10, 9.20, 8.90, 9.00)]
WIN_S2 = [("09:30", 8.80, 9.00, 8.50, 8.60), ("09:34", 8.60, 8.70, 8.30, 8.40), ("15:59", 8.40, 8.50, 8.00, 8.10)]
WIN_S3 = [("09:30", 8.10, 8.20, 7.80, 7.90), ("15:59", 7.90, 8.00, 7.50, 7.60)]

FLAT_21 = [("09:30", 21.00, 21.00, 21.00, 21.00), ("15:59", 21.00, 21.00, 21.00, 21.00)]

FIXTURES = {
    # name: {"minutes": {session: bars or None (absent from the minute file)}, "daily": {session: "bar" | "hole" | "ended"},
    #        "adr20": float, "raw_last": the raw close of the last walked daily bar (ended_mid_walk), "closes": daily closes for the class}
    "1_win_time_exit": {
        "minutes": {S1: WIN_S1, S2: WIN_S2, S3: WIN_S3}, "daily": {S1: "bar", S2: "bar", S3: "bar"}, "adr20": 0.10},
    "2_stopped_day_high": {
        "minutes": {S1: [("09:30", 20.00, 20.80, 19.90, 20.50), ("09:31", 20.50, 21.00, 20.40, 20.90), ("09:32", 20.90, 21.20, 20.70, 20.80),
                         ("09:33", 20.80, 20.90, 20.30, 20.40), ("09:34", 20.40, 20.50, 20.00, 20.10), ("09:35", 20.10, 20.20, 19.85, 19.95),
                         ("09:40", 19.95, 20.50, 19.90, 20.40), ("10:00", 20.40, 21.30, 20.30, 21.00), ("15:59", 21.00, 21.10, 20.90, 21.00)],
                    S2: FLAT_21, S3: FLAT_21},
        "daily": {S1: "bar", S2: "bar", S3: "bar"}, "adr20": 0.10},
    "3_never_triggered": {
        "minutes": {S1: [("09:30", 5.00, 5.20, 4.90, 5.10), ("09:31", 5.10, 5.30, 5.00, 5.20), ("09:32", 5.20, 5.25, 4.95, 5.00),
                         ("09:33", 5.00, 5.10, 4.96, 5.05), ("09:34", 5.05, 5.15, 5.00, 5.10), ("09:35", 5.10, 5.15, 4.90, 5.00),
                         ("10:00", 5.00, 5.20, 4.95, 5.10), ("15:59", 5.10, 5.30, 5.00, 5.20)],
                    S2: [("09:30", 5.20, 5.30, 4.50, 4.60), ("15:59", 4.60, 4.70, 4.40, 4.50)],
                    S3: [("09:30", 4.50, 4.60, 4.00, 4.10), ("15:59", 4.10, 4.20, 3.90, 4.00)]},
        "daily": {S1: "bar", S2: "bar", S3: "bar"}, "adr20": 0.10},
    "4_gap_through": {
        "minutes": {S1: [("09:30", 30.50, 31.00, 30.20, 30.60), ("09:31", 30.60, 30.90, 30.30, 30.40), ("09:32", 30.40, 30.70, 30.00, 30.20),
                         ("09:33", 30.20, 30.50, 30.10, 30.30), ("09:34", 30.30, 30.60, 30.10, 30.20), ("09:35", 29.50, 29.60, 29.20, 29.30),
                         ("15:59", 29.30, 29.40, 29.00, 29.10)],
                    S2: [("09:30", 29.00, 29.20, 28.00, 28.10), ("15:59", 27.00, 27.10, 26.90, 27.00)],
                    S3: [("09:30", 26.90, 27.00, 25.00, 25.10), ("15:59", 24.10, 24.20, 23.90, 24.00)]},
        "daily": {S1: "bar", S2: "bar", S3: "bar"}, "adr20": 0.10},
    "5_same_bar_tie": {
        "minutes": {S1: WIN_S1, S2: WIN_S2, S3: [("09:30", 8.10, 8.20, 7.80, 7.90), ("15:59", 8.00, 10.80, 7.90, 8.00)]},
        "daily": {S1: "bar", S2: "bar", S3: "bar"}, "adr20": 0.10},
    "6_time_exit_loser": {
        "minutes": {S1: WIN_S1, S2: [("09:30", 9.00, 9.30, 8.90, 9.20), ("15:59", 9.50, 9.60, 9.40, 9.50)],
                    S3: [("09:30", 9.60, 9.90, 9.50, 9.80), ("15:59", 10.20, 10.40, 10.10, 10.30)]},
        "daily": {S1: "bar", S2: "bar", S3: "bar"}, "adr20": 0.10},
    "7_stopped_at_session_open": {
        "minutes": {S1: WIN_S1, S2: [("09:30", 11.00, 11.20, 10.90, 11.10), ("15:59", 11.10, 11.30, 11.00, 11.20)], S3: FLAT_21},
        "daily": {S1: "bar", S2: "bar", S3: "bar"}, "adr20": 0.10},
    "8_minute_missing": {
        "minutes": {S1: WIN_S1, S2: None, S3: WIN_S3}, "daily": {S1: "bar", S2: "bar", S3: "bar"}, "adr20": 0.10},
    "9_no_orb": {
        "minutes": {S1: [("09:40", 10.05, 10.10, 9.70, 9.75), ("15:59", 9.10, 9.20, 8.90, 9.00)], S2: WIN_S2, S3: WIN_S3},
        "daily": {S1: "bar", S2: "bar", S3: "bar"}, "adr20": 0.10},
    "9b_no_0930_bar": {        # the first bar starts 09:31: no opening minute -> no range, for every range width (review LOW, 11-01)
        "minutes": {S1: [("09:31", 10.20, 10.60, 10.10, 10.40), ("09:32", 10.40, 10.70, 10.30, 10.50), ("09:40", 10.05, 10.10, 9.70, 9.75),
                         ("15:59", 9.10, 9.20, 8.90, 9.00)], S2: WIN_S2, S3: WIN_S3},
        "daily": {S1: "bar", S2: "bar", S3: "bar"}, "adr20": 0.10},
    "10_ended_mid_walk_collapse": {
        "minutes": {S1: WIN_S1, S2: [("09:30", 8.80, 9.00, 8.50, 8.60), ("15:59", 0.70, 0.75, 0.55, 0.60)], S3: None},
        "daily": {S1: "bar", S2: "bar", S3: "ended"}, "adr20": 0.10, "raw_last": 0.60, "closes": [10.0, 9.0, 0.60]},
    "11_void_geometry": {
        "minutes": {S1: [("09:30", 10.02, 10.05, 10.00, 10.03), ("09:31", 10.03, 10.04, 10.01, 10.02), ("09:32", 10.02, 10.05, 10.00, 10.04),
                         ("09:33", 10.04, 10.05, 10.02, 10.03), ("09:34", 10.03, 10.04, 10.00, 10.01), ("09:35", 10.01, 10.02, 9.98, 9.99),
                         ("15:59", 9.99, 10.00, 9.90, 9.95)],
                    S2: FLAT_21, S3: FLAT_21},
        "daily": {S1: "bar", S2: "bar", S3: "bar"}, "adr20": 0.10},
    "12_outside_entry_bar": {  # review HIGH #2 case A: the entry bar breaks the range low AND runs through the prior high in one minute
        "minutes": {S1: WIN_S1[:5] + [("09:35", 10.30, 11.50, 9.70, 11.40), ("15:59", 11.40, 11.45, 11.30, 11.40)],
                    S2: [("09:30", 11.40, 11.40, 11.40, 11.40), ("15:59", 11.40, 11.40, 11.40, 11.40)],
                    S3: [("09:30", 11.40, 11.40, 11.40, 11.40), ("15:59", 11.40, 11.40, 11.40, 11.40)]},
        "daily": {S1: "bar", S2: "bar", S3: "bar"}, "adr20": 0.10},
    "13_gap_through_then_rally": {  # review HIGH #2 case B: a gap-through fill at the open, then the same bar rallies through the prior high
        "minutes": {S1: WIN_S1[:5] + [("09:35", 9.50, 10.90, 9.40, 10.80), ("15:59", 9.00, 9.10, 8.90, 9.00)],
                    S2: [("09:30", 9.00, 9.00, 9.00, 9.00), ("15:59", 9.00, 9.00, 9.00, 9.00)],
                    S3: [("09:30", 8.00, 8.00, 8.00, 8.00), ("15:59", 8.00, 8.00, 8.00, 8.00)]},
        "daily": {S1: "bar", S2: "bar", S3: "bar"}, "adr20": 0.10},
}

# ---- the hand numbers (the registration's §8 table; every one written before the code ran) ------------------------------------------
# key = (fixture, variant) ; variant = f"o{orb_minutes}h{hold}" ; value = the fields that must match
EXPECTED = {
    ("1_win_time_exit", "o5h3"): {"status": "settled", "reason": "time_stop", "entry": 9.79, "stop": 10.71, "risk": 0.92, "exit": 7.60,
                                  "r": 2.380434782608696, "sessions_held": 3, "r_slip1": 2.372173913043478, "r_slip2": 2.363913043478261,
                                  "mfe": 2.489130434782609, "mae": 0.119565217391304, "pnl_adr": 2.236976506639428, "win": 1},
    ("1_win_time_exit", "o5h1"): {"status": "settled", "reason": "time_stop", "exit": 9.00, "r": 0.858695652173913, "sessions_held": 1},
    ("1_win_time_exit", "o5h2"): {"status": "settled", "reason": "time_stop", "exit": 8.10, "r": 1.836956521739130, "sessions_held": 2},
    ("1_win_time_exit", "o15h3"): {"status": "settled", "reason": "time_stop", "entry": 9.69, "stop": 10.71, "risk": 1.02, "r": 2.049019607843137},
    ("1_win_time_exit", "o1h3"): {"status": "settled", "reason": "time_stop", "entry": 9.79, "stop": 10.71, "r": 2.380434782608696},
    ("2_stopped_day_high", "o5h3"): {"status": "settled", "reason": "stop", "entry": 19.89, "stop": 21.21, "risk": 1.32, "exit": 21.21,
                                     "r": -1.0, "sessions_held": 1, "exit_session": S1, "mae": 1.0, "win": 0},
    ("3_never_triggered", "o5h3"): {"status": "untriggered"},
    ("4_gap_through", "o5h3"): {"status": "settled", "reason": "time_stop", "entry": 29.50, "stop": 31.01, "risk": 1.51, "exit": 24.00,
                                "r": 3.642384105960265, "sessions_held": 3},
    ("5_same_bar_tie", "o5h3"): {"status": "settled", "reason": "stop", "exit": 10.71, "r": -1.0, "sessions_held": 3},
    ("6_time_exit_loser", "o5h3"): {"status": "settled", "reason": "time_stop", "exit": 10.30, "r": -0.554347826086957, "sessions_held": 3},
    ("7_stopped_at_session_open", "o5h3"): {"status": "settled", "reason": "stop", "exit": 11.00, "r": -1.315217391304348, "sessions_held": 2,
                                            "exit_session": S2},
    ("8_minute_missing", "o5h3"): {"status": "minute_missing_open"},
    ("9_no_orb", "o5h3"): {"status": "no_orb"},
    ("9_no_orb", "o15h3"): {"status": "no_orb"},                 # the 15-minute range too: no 09:30 bar, no range (review LOW)
    ("9b_no_0930_bar", "o5h3"): {"status": "no_orb"},
    ("9b_no_0930_bar", "o1h3"): {"status": "no_orb"},
    ("9b_no_0930_bar", "o15h3"): {"status": "no_orb"},
    ("10_ended_mid_walk_collapse", "o5h3"): {"status": "ended_mid_walk", "last_close": 0.60, "r_last_close": 9.989130434782609,
                                             "r_haircut": 9.826086956521739, "ended_class": "collapse"},
    ("11_void_geometry", "o5h3"): {"status": "void_bad_geometry", "entry": 9.99, "stop": 10.06},
    # the stop = the highest high BEFORE the entry bar + 1c; an entry bar whose high reaches it books the stop on that bar (-1R)
    ("12_outside_entry_bar", "o5h3"): {"status": "settled", "reason": "stop", "entry": 9.79, "stop": 10.71, "risk": 0.92, "exit": 10.71,
                                       "r": -1.0, "sessions_held": 1, "exit_ts": "09:35", "entry_ts": "09:35", "ambiguous_entry_bar": 1,
                                       "mae": 1.0, "mfe": 0.0, "r_tick1": -1.021739130434783, "r_tick2": -1.043478260869565,
                                       "r_tick5": -1.108695652173913},
    ("12_outside_entry_bar", "o5h3x"): {"status": "settled", "reason": "time_stop", "entry": 9.79, "stop": 11.51, "risk": 1.72, "exit": 11.40,
                                        "r": -0.936046511627907, "sessions_held": 3},      # the beside rule (the entry bar's high inside the stop)
    ("13_gap_through_then_rally", "o5h3"): {"status": "settled", "reason": "stop", "entry": 9.50, "stop": 10.71, "risk": 1.21, "exit": 10.71,
                                            "r": -1.0, "sessions_held": 1, "ambiguous_entry_bar": 1},
    ("13_gap_through_then_rally", "o5h3x"): {"status": "settled", "reason": "time_stop", "entry": 9.50, "stop": 10.91, "risk": 1.41, "exit": 8.00,
                                             "r": 1.063829787234043, "sessions_held": 3},
    # the tick-slippage beside rows on #1 (entry 1 / 2 / 5 cents lower, the cover 1 / 2 / 5 cents higher; R_k = R - 2k / risk)
    ("1_win_time_exit", "o5h3+"): {"r_tick1": 2.358695652173913, "r_tick2": 2.336956521739130, "r_tick5": 2.271739130434783,
                                   "ambiguous_entry_bar": 0, "pnl_adr_tick1": 2.216547497446374},
    ("4_gap_through", "o5h3+"): {"ambiguous_entry_bar": 0},
    ("2_stopped_day_high", "o5h3+"): {"ambiguous_entry_bar": 0},
}
