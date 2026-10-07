"""#624 backfill — the walkers. PRIMARY = the live lane walker's own functions, called on captured data in the
order lowcap_lane_replay._record_one_signal calls them (prereg §3). S1 / S2 = the #687 / #685 chain, unchanged.

Declared deviations from the live walker (prereg §3): day-0 bars are Polygon's; a stock whose daily bars END before
its 40th session and before the data end is closed at its last close ('delisted_forced_close'); a missing session
INSIDE the series still blocks ('unscoreable'). Nothing here reads an outcome table.
"""
from __future__ import annotations

import sys
from datetime import date, datetime, time, timedelta

import lib624 as L

from agents.market_intelligence import live_fill_counterfactuals as lfc  # noqa: E402
from agents.market_intelligence import rule_eras  # noqa: E402
from agents.market_intelligence import sustain_reject_replay as srr  # noqa: E402
from agents.market_intelligence.alert_rank_shadow import compute_atr14_prior  # noqa: E402
from agents.market_intelligence.backtester.filters import validate_orb_entry  # noqa: E402
from agents.market_intelligence.lowcap_lane_replay import (  # noqa: E402
    ATR_LOOKBACK_CAL_DAYS, PRIOR_CLOSES_CAL_DAYS, SPLIT_DIVERGENCE_ABS_PCT)

RUN_DATE = L.TODAY
RULES_D = rule_eras.exit_rules_as_of(RUN_DATE, "magna53")
assert rule_eras.exit_era_label(RUN_DATE, "magna53") == "era_d"
assert (RULES_D["stop_mode"], RULES_D["intraday_partial_r"], RULES_D["breakeven_at_r"]) == ("entry_minus_2r", 8.0, 3.0)

_TD_CACHE: dict = {}


def trading_days_after(d: date, last: date, n: int = lfc.HORIZON_SESSIONS) -> list[date]:
    k = (d, last)
    if k not in _TD_CACHE:
        _TD_CACHE[k] = lfc._trading_days(d + timedelta(days=1), last)[:n]
    return _TD_CACHE[k]


def assemble_sessions(dl: dict | None, d: date, last_session: date) -> list[tuple[date, dict | None]]:
    """lfc._assemble_sessions' shape from the captured daily rows: [(date, bar|None)] for the trading sessions after
    d through last_session, capped at HORIZON_SESSIONS. (No live single-day fallback here: a missing stored row is None.)"""
    out = []
    rows = (dl or {}).get("rows", {})
    for x in trading_days_after(d, last_session):
        r = rows.get(x)
        bar = None
        if r is not None and r["c"] is not None and r["h"] is not None and r["l"] is not None:
            bar = {"o": r["o"], "h": r["h"], "l": r["l"], "c": r["c"]}
        out.append((x, bar))
    return out


def _prior(dl: dict | None, d: date):
    rows = (dl or {}).get("rows", {})
    ds = [x for x in (dl or {}).get("dates", []) if d - timedelta(days=ATR_LOOKBACK_CAL_DAYS) <= x <= d]
    day0_row = rows.get(d)
    prior = [(x, rows[x]) for x in ds if x != d]
    prior_hlc = [(r["h"], r["l"], r["c"]) for _, r in prior]
    prior_hlc = [t for t in prior_hlc if all(v is not None for v in t)]
    cut = d - timedelta(days=PRIOR_CLOSES_CAL_DAYS)
    prior_closes = [float(r["c"]) for x, r in prior if r["c"] is not None and x >= cut]
    return day0_row, prior_hlc, prior_closes


def _finish(res: dict, entry: float, risk: float, bars0, sessions, dl, data_end: date, out: dict) -> dict:
    status = res["status"]
    last_row = (dl or {}).get("dates", [None])[-1] if dl and dl.get("dates") else None
    out.update(partial_fired=res.get("partial_fired"), gap_through=res.get("gap_through"),
               exit_session=res.get("exit_session"), sessions_walked=res.get("sessions_walked"),
               final_reason=res.get("final_reason") or res.get("reason"))
    if status == "pending":
        gap = res.get("pending_at")
        if gap is not None:
            # the first missing session lies AFTER the ticker's last stored row, and the ticker stopped before the
            # data end -> it stopped trading: close at the last close (declared deviation (ii))
            if last_row is not None and last_row < data_end and gap > last_row:
                mark = srr.mark_pnl_per_share(res, bars0, sessions, entry)
                if mark is not None:
                    out.update(outcome="delisted_forced_close", R=mark / risk, settled=True, forced=True,
                               final_reason="delisted_forced_close", exit_day=last_row)
                    return out
            out.update(outcome="unscoreable", final_reason=f"missing_session:{gap}")
            return out
        mark = srr.mark_pnl_per_share(res, bars0, sessions, entry)
        out.update(outcome="open", R=None if mark is None else mark / risk, marked=True)
        return out
    if status == "settled":
        pnl = res.get("pnl_per_share")
        out.update(outcome="settled", R=None if pnl is None else pnl / risk, settled=True)
        ex = res.get("exit_session")
        out["exit_day"] = (sessions[ex - 1][0] if ex and 0 < ex <= len(sessions) else None)
        return out
    if status == "horizon":
        mark = res.get("mark_pnl_per_share")
        out.update(outcome="horizon", R=None if mark is None else mark / risk, marked=True)
        return out
    out.update(outcome="unscoreable", final_reason=res.get("reason"))   # abstain (same-bar ambiguity)
    return out


def walk_primary(t: str, d: date, T: time, bars0: list[dict], dl: dict | None, *, rules: dict = RULES_D,
                 run_date: date = RUN_DATE, last_session: date = L.DATA_END, data_end: date = L.DATA_END,
                 entry_mode: str = "stop_limit") -> dict:
    """One signal through the live lane walker. entry_mode 'stop_limit' = srr.entry_walk (PRIMARY);
    'live_order' = _687/backfill.live_entry (S1, the #500 price-aware order) with the same forward walk."""
    out = {"t": t, "d": d, "T": T, "outcome": None, "entry_status": None, "R": None, "settled": False,
           "marked": False, "forced": False}
    submit, oor = srr.submit_time_and_window(datetime.combine(d, T, tzinfo=L.ET))
    out["submit"] = submit
    if oor:
        out.update(entry_status="window_out_of_orb", outcome="no_trade", final_reason="window_out_of_orb")
        return out
    sessions = assemble_sessions(dl, d, last_session)
    day0_row, prior_hlc, prior_closes = _prior(dl, d)
    atr14 = compute_atr14_prior(prior_hlc)
    out["atr14_prior"] = atr14
    if not bars0:
        out.update(entry_status="no_day0_minute_bars", outcome="unscoreable", final_reason="no_day0_minute_bars")
        return out
    orb = next((b for b in bars0 if b["m"].time() == time(9, 30)), None)
    if orb is None:
        out.update(entry_status="no_930_bar_for_orb", outcome="unscoreable", final_reason="no_930_bar_for_orb")
        return out
    H, Lw = orb["h"], orb["l"]
    out.update(orb_high=H, orb_low=Lw)
    daily_open = day0_row["o"] if day0_row else None
    if daily_open and orb["o"] and abs(daily_open / orb["o"] - 1) > SPLIT_DIVERGENCE_ABS_PCT:
        out.update(entry_status="daily_row_split_adjusted", outcome="unscoreable", final_reason="daily_row_split_adjusted")
        return out
    ok, skip = validate_orb_entry(H, Lw, atr14)
    if not ok:
        out.update(entry_status="orb_invalid", outcome="no_trade", final_reason=skip)
        return out
    cancel = srr.entry_cancel_asof(run_date)
    if entry_mode == "stop_limit":
        fill = srr.entry_walk(bars0, H, submit, cancel)
    else:
        import s1s2
        fill = s1s2.live_entry(bars0, H, Lw, submit)
    out.update(entry_status=fill["status"], entry_reason=fill.get("reason"), fill_kind=fill.get("kind"))
    if fill["status"] != "filled":
        out.update(outcome="unscoreable" if fill["status"] == "abstain" else "no_trade", final_reason=fill.get("reason"))
        return out
    entry = fill["px"]
    out.update(entry_price=entry, entry_minute=fill["minute"])
    stop = srr.current_era_stop(rules["stop_mode"], H, Lw)
    risk = entry - stop
    if risk <= 0:
        out.update(outcome="unscoreable", final_reason="nonpositive_risk_per_share")
        return out
    out.update(stop=stop, risk=risk, stop_pct_of_entry=(entry - stop) / entry * 100)
    target, kw = lfc.stack_walk_inputs(rules, entry, Lw)
    fill_idx = next(i for i, b in enumerate(bars0) if b["m"] == fill["minute"])
    res = lfc.walk_arm(entry=entry, stop=stop, target=target, day0_bars=bars0, fill_idx=fill_idx, sessions=sessions,
                       prior_closes=prior_closes, harvest="live_ladder", fill_day=d, **kw)
    out["_fill"] = {"px": entry, "minute": fill["minute"], "kind": fill.get("kind")}
    return _finish(res, entry, risk, bars0, sessions, dl, data_end, out)
