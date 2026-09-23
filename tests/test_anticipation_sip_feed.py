"""#270 Step 3 — anticipation → mi_stocks_in_play feed (ADR 0004 consolidation).

A anticipation row that reaches ready/triggered ALSO surfaces in the unified /watch
board (one row per detector); /sip stays the drill-down. These pin the two things a
future edit could silently break: (1) the new source_detector is registered in
VALID_SOURCES (ADR 0004 friction-by-design — unregistered sources raise at insert),
and (2) the readiness_signal is JSON-native (Decimals floated, dates pre-stringified)
so the plain-json.dumps jsonb codec can't choke — the exact hazard the sugar-baby
site dodges by str()-ing its dates.
"""
import json
from decimal import Decimal

import agents.market_intelligence.anticipation as de
from agents.market_intelligence.stocks_in_play_sources import (
    SOURCE_ANTICIPATION_REENTRY, CLASS_OPERATOR_ONLY, VALID_SOURCES,
    validate_source, validate_class,
)


def test_source_registered():
    assert SOURCE_ANTICIPATION_REENTRY in VALID_SOURCES
    assert validate_source(SOURCE_ANTICIPATION_REENTRY) == SOURCE_ANTICIPATION_REENTRY
    # the feed writes operator_only (never apollo_eligible while shadow)
    assert validate_class(CLASS_OPERATOR_ONLY) == CLASS_OPERATOR_ONLY


def test_ready_payload_has_no_entry_and_reads_as_setup():
    reason, signal = de.sip_payload(
        state="ready", gap_day_iso="2026-05-26", base_run=4, rmv_5d=Decimal("8.3"))
    assert "ready" in reason.lower()
    assert signal["state"] == "ready"
    assert signal["gap_day"] == "2026-05-26"
    assert signal["entry_price"] is None and signal["stop_price"] is None
    json.dumps(signal)  # must not raise — Decimal rmv_5d was floated


def test_triggered_first5_payload_is_json_safe_with_decimals():
    # entry/stop/rmv arrive as Decimals from asyncpg NUMERIC columns; the
    # plain-json.dumps jsonb codec would TypeError on a raw Decimal.
    reason, signal = de.sip_payload(
        state="triggered", gap_day_iso="2026-05-26", entry_tactic="first5_break",
        entry_price=Decimal("12.40"), stop_price=Decimal("11.90"),
        base_run=5, rmv_5d=Decimal("6.1"))
    assert reason == "anticipation first5 entry @ 12.40"
    assert signal["entry_tactic"] == "first5_break"
    assert isinstance(signal["entry_price"], float)
    assert isinstance(signal["rmv_5d"], float)
    json.dumps(signal)  # the codec-choke guard


def test_anticipation_and_gdl_tactic_labels():
    r_anti, _ = de.sip_payload(
        state="triggered", gap_day_iso="2026-06-01", entry_tactic="anticipation",
        entry_price=9.5)
    assert r_anti == "anticipation anticip entry @ 9.50"
    r_gdl, _ = de.sip_payload(
        state="triggered", gap_day_iso="2026-06-01", entry_tactic="gdl_reclaim",
        entry_price=9.5)
    assert r_gdl == "anticipation gdl entry @ 9.50"
