"""Feature 3, re-defined — 'the pullbacks held the top of the base the stock broke out of before its run'.

The exact definition lives in F3_DEFINITION.md (same folder). ITS ONLY IMPLEMENTATION MOVED on 2026-11-21 (#594) to
`agents/market_intelligence/shelf_distance.py`, unchanged, so the live slot-rank record and every analysis script
(kod_check.py, rank_v2_f3.py, the score_shelf_lead.py runs) share one definition. This file re-exports it — do not
re-define anything here (pinned by tests/test_594_shelf_rank_shadow.py).

days = [(trade_date, o, h, l, c, v), ...] sorted, sliced to the 5 calendar years before D (rank_v2.py's slice5);
ia = index of D in days; adr = ADR20 % (the encoder's adr20_pct, shared with feature 1).
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO = str(Path(__file__).resolve().parents[4])
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from agents.market_intelligence.shelf_distance import (  # noqa: E402,F401
    PIVOT_WING, STATED, _argmax_latest, _argmin_latest, f3_new, swing_lows,
)
