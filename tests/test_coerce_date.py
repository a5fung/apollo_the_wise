"""S7/F12 — db._coerce_date, the wire-boundary str->date coercion helper.

Consolidates what used to be 4 in-function `_dd` closures in db.py plus an inline
isinstance block in broker/live_tracker.py::_insert_skipped_trade into one shared
helper (LZB 2026-06-13: a missed coercion site 500-ed a HIGH alert's terminal
skipped-trade row when the alert_date crossed the intelligence->execution HTTP
wire as an ISO string). Pure logic — no DB required.
"""
from __future__ import annotations

from datetime import date

from agents.market_intelligence.db import _coerce_date


def test_coerce_date_converts_iso_string():
    assert _coerce_date("2026-06-13") == date(2026, 6, 13)


def test_coerce_date_passes_through_date_object():
    d = date(2026, 6, 13)
    assert _coerce_date(d) is d


def test_coerce_date_passes_through_none():
    assert _coerce_date(None) is None
