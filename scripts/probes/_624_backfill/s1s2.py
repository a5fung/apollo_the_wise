"""#624 backfill — sensitivities S1 / S2 on the SAME signals, via the #687 / #685 machinery IMPORTED UNCHANGED.

S1: _687/backfill.live_entry (the #500 price-aware live order, chase-or-skip above the ORB high) with the tick-derived
    submit; the forward walk is the PRIMARY walker's (walk624.walk_primary(entry_mode='live_order')).
S2: _687/backfill.day0_from_fill + walk_trail_arm('A0', ...) + force_close_delisted on the PRIMARY fill (the #685
    forward walk: minute walk on line-test days, daily otherwise, to the data end — no 40-session cap).
The only runtime setting: backfill.HORIZON (used by force_close_delisted) is set to this run's data end, exactly as
#687 itself sets study.ADR_MULT at call time.
"""
from __future__ import annotations

import sys
from datetime import date, time

import lib624 as L

sys.path.insert(0, str(L.REPO / "scripts/probes/_687"))
sys.path.insert(0, str(L.REPO / "scripts/probes/_685"))
_argv = sys.argv
sys.argv = [sys.argv[0]]
import backfill as BF  # noqa: E402
sys.argv = _argv
from agents.market_intelligence.sustain_reject_replay import _stop_limit_buy_price  # noqa: E402

BF.HORIZON = L.DATA_END


def live_entry(bars0, H, Lw, submit: time) -> dict:
    return BF.live_entry(bars0, H, Lw, "open", submit)


def fill_kind(px: float, H: float) -> str:
    if abs(px - H) < 1e-9:
        return "cross"
    if abs(px - _stop_limit_buy_price(H)) < 1e-9:
        return "limit_pullback"
    return "open_in_band"


def s2_walk(t: str, d: date, bars0, H: float, Lw: float, fill: dict, daily_bf: dict, held: dict) -> dict:
    f = {"px": fill["px"], "minute": fill["minute"]}
    f["kind"] = fill.get("kind") or fill_kind(fill["px"], H)
    f["fill_at_open"] = f["kind"] in ("open_in_band", "chase_open")
    st, why = BF.day0_from_fill(t, d, bars0, H, Lw, f, daily_bf)
    if st is None:
        return {"status": "excluded", "why": why, "R": None, "line_tests": []}
    if st["settled_d0"]:
        return {"status": "settled", "R": st["h"]["realized_r"], "day0": True, "line_tests": [], "forced": False}
    r = BF.walk_trail_arm("A0", t, d, st, daily_bf, held, horizon=L.DATA_END)
    r = BF.force_close_delisted(r, t, daily_bf)
    R = r["realized_r"] if r["status"] == "settled" else r.get("mark_r")
    return {"status": r["status"], "R": R, "day0": False, "line_tests": r.get("line_tests", []),
            "forced": bool(r.get("delisted_forced_close")), "final": r.get("final_reason")}
