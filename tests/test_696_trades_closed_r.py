"""#696 — /trades 'Last 5 Closed' shows each trade's realized R and no attempts suffix.

R comes from `sell_discipline.trade_realized_r` (the one formula the sell-discipline record
uses), so the two surfaces cannot disagree. Display only.
"""
import json
from datetime import datetime, timezone

from agents.market_intelligence import sell_discipline as sd
from agents.market_intelligence.closed_trade_line import fmt_closed_line

# VICR trade #400, read-only from prod 2026-10-09 (scripts/probes/_696/vicr_400_row.txt;
# the stored sell-discipline record for it is realized_r = 7.3029, vicr_400_record.txt).
_VICR_400 = {
    "id": 400, "ticker": "VICR", "entry_price": 211.5, "hard_stop": 201.13010000000003,
    "orb_low": 206.55, "entry_shares": 1, "total_pnl": 75.73000000000002, "hold_days": 19,
    "ep_score": 71, "closed_at": datetime(2026, 10, 7, 13, 30, tzinfo=timezone.utc),
    "exits": json.dumps([{"price": 287.23, "shares": 1, "pnl": 75.73, "reason": "stop_hit"}]),
}


def _parse(raw):
    return raw if isinstance(raw, list) else json.loads(raw or "[]")


def test_closed_line_renders_realized_r_and_no_attempts_suffix():
    lines = fmt_closed_line(_VICR_400, parse_exits=_parse)
    assert lines[0] == "  ✅ *VICR* $+76 · +7.3R (19d) · Oct 07"
    assert "attempt" not in "\n".join(lines)


def test_vicr_400_r_pins_to_the_sell_discipline_value():
    shown = sd.trade_realized_r(_VICR_400)
    assert shown == 7.3029  # == the stored mi_sell_discipline_records.realized_r for #400
    assert f"{shown:+.1f}R" in fmt_closed_line(_VICR_400, parse_exits=_parse)[0]


def test_compute_sell_record_uses_the_same_helper():
    row = dict(_VICR_400, filled_at=datetime(2026, 9, 18, 13, 31, tzinfo=timezone.utc))
    rec = sd.compute_sell_record(row)
    assert rec is not None and rec["realized_r"] == sd.trade_realized_r(_VICR_400)


def test_no_risk_unit_renders_no_r_never_a_made_up_one():
    stripped = {k: v for k, v in _VICR_400.items() if k not in ("hard_stop", "orb_low", "entry_shares")}
    for broken in (dict(_VICR_400, hard_stop=None, orb_low=None),    # no stop at all
                   dict(_VICR_400, hard_stop=215.0, orb_low=216.0),  # stop above entry
                   dict(_VICR_400, entry_shares=None),               # no shares
                   stripped):                                        # columns not selected
        assert sd.trade_realized_r(broken) is None
        assert fmt_closed_line(broken, parse_exits=_parse)[0] == "  ✅ *VICR* $+76 (19d) · Oct 07"


def test_orb_low_fallback_and_losing_trade_sign():
    loser = dict(_VICR_400, hard_stop=None, entry_price=100.0, orb_low=95.0, entry_shares=10,
                 total_pnl=-50.0)
    assert sd.trade_realized_r(loser) == -1.0
    assert "-1.0R" in fmt_closed_line(loser, parse_exits=_parse)[0]
