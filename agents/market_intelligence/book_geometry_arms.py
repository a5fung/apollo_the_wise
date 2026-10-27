"""2026-10-26 — #482 BOOK ARMS: the Qullamaggie entry and stop, recorded beside every live MAGNA53 fill.

WHY (operator 2026-10-06, his book comparison, `docs/methodology/operator_shared_notes.md` TEST MAP
— "No changes but worth comparing and see where we can test and tweak as we refine our system"):
the book buys ABOVE THE FIRST 5-MINUTE BAR (the first 1-HOUR bar when volume is unconfirmed) with
the stop at the LOW OF THE DAY. We buy the first 1-minute bar's high with the stop at entry − 2R. This
module records what those book rules would have produced on the same fill, the same stored bars, the
same exit ladder, the same 40-session horizon and the same era stamp as every other arm in
`mi_live_fill_counterfactuals`:

  stop_low_of_day        the LIVE entry (the real fill); the stop at the LOW OF THE DAY — the lowest
                         1-minute low of the regular session strictly BEFORE the fill bar. (The fill
                         bar's own low is excluded: it straddles the trigger, so its order against
                         the fill is unknowable at 1-min grain and `walk_arm` would abstain on every
                         row; excluding it also keeps the stop knowable at order time.) Regular
                         session only — stored bars start 09:30, so a pre-market low is out of
                         reach; on a 09:31 fill this equals the ORB low (stop_orb_low), and it only
                         differs once the day has undercut the opening bar before a later fill —
                         so on most fills it DUPLICATES stop_orb_low (said, not hidden).
  entry_first_hour_bar   the ENTRY moves to the first 60-minute bar (09:30-10:29 ET): a stop-limit
                         buy at that bar's HIGH, submitted 10:30, day order to the session's close
                         (13:00 on a half day — `session_close_et`), with the live broker's own limit
                         buffer (`entry_walk`, mirrored from sustain_reject_replay.entry_walk — the
                         micro-structure replay validated against real fills). The LIVE bracket rule
                         restated on that bar and nothing else: stop = 2 × bar low − bar high
                         (= entry − 2R in the bar's frame, the formula `prepare_orb_order` uses), the
                         +N R target and the price-armed breakeven pinned to the bar's R
                         (entry − bar low). A bar high never retaken is NOT a loss: it is
                         `unscoreable` with `final_reason` 'no_entry:never_crossed_hour_high' — no
                         trade, counted apart from missing data by the reason's prefix. NO live
                         admission gate is applied (the `stop_too_wide` ATR gate would refuse most
                         hour bars); `stop_width_adr` states the width so a reader can cut it offline.
  book_first_hour_low_of_day
                         THE BOOK AS A UNIT (review F3, 2026-10-26): the first-hour-bar entry above
                         AND the low-of-day stop together — the stop at the lowest 1-minute low
                         strictly before ITS OWN fill bar (so the hour bar's low, or anything lower
                         printed between 10:30 and the fill). Target and breakeven pinned to the
                         hour bar's R exactly as `entry_first_hour_bar`, so against that arm the
                         ONLY thing that moves is the stop, and against `stop_low_of_day` the only
                         thing that moves is the entry.
  fill_facts             NOT a walked arm (review F1): one write-once row per fill, written on the
                         fill's FIRST night, carrying the LIVE fill's fill-vs-trigger facts. They are
                         entry-time facts and must not wait up to 40 sessions for an exit walk to
                         settle. outcome 'unscoreable', final_reason 'fill_facts_only'; it has no
                         stop, no target and no result, and nothing pins a fill's levels to it.

SELECTION EFFECT (review F3) — read this before quoting any of these arms. This recorder sees ONLY the
fills we took: the names whose 1-MINUTE ORB high filled (~15 MAGNA53 fills since 2026-08-16 at the
2026-10-11 count). The hour-bar arms therefore answer "GIVEN we entered at the 1-minute high, would
the hour bar have paid" — an alert that never took the 1-minute high but did take the hour high is
invisible here, and at the probe's ~42% hour-arm entry rate only a handful of rows per arm will be
entered trades. The TEST MAP put the entry test on the 5-minute ORB shadow lane's full alert
population (`mi_orb_shadow_trades`); he said yes on 2026-10-26, and `broker/shadow_orb_tracker
.run_shadow_hour_pass` records the hour-bar entry there as `bar_size_minutes = 60` on the SAME walk
(docs/setups/magna53_ep.md 2026-10-27).

THE HOUR-BAR WALK IS SHARED. `stop_limit_buy_price`, `entry_walk`, `first_hour_frame`,
`session_close_et` and `classify_hour_entry` live in `broker/hour_bar_walk.py` (pure math, no Alpaca
client — the `exit_logic` precedent) since 2026-10-27, so the two recorders cannot drift and the
execution deploy scope covers the copy the shadow tracker runs; this module re-exports them under
their old names. THE DAY-0 GAP RULE (review F4) is stated there: a walk with holes after 10:30 and no
stored cross is decided by the stored day-0 DAILY high — strictly below the hour high proves the
no-entry (':proven_by_daily_high'); equal or higher, or no stored daily bar, leaves the hour arm —
like a thin first hour — on the original recorder's gap rule: PENDING, retried nightly, written
`abstain` with the reason named only once the gap is GAP_RETRY_SESSIONS old.

THE CAPPED-DOLLAR COLUMNS (the 2026-10-06 H10 lesson — `docs/analysis/327_h10_h11_2026-10-06.md`:
"any stop proposal must be scored in capped dollars beside R"). SIZE OFF THE TRIGGER, RESULT OFF THE
FILL (review F5), exactly as `prepare_orb_order` sizes: risk budget = equity × RISK_PCT × regime
multiplier, shares = budget / (TRIGGER − stop), then the 20% notional cap at the TRIGGER price. In
units of ONE full R (equity × RISK_PCT), equity cancels:
    risk_frac_capped = min(mult × (fill − stop) / (trigger − stop),
                           MAX_POSITION_PCT × (fill − stop) / (trigger × RISK_PCT_at_fill))
    cap_binding      = the second term is the smaller (the notional cap, not the budget, set the size)
    realized_r_capped = realized_r × risk_frac_capped     (realized_r is in the FILL's own units)
The trigger used is the row's own `orb_high` (the live ORB high on stop_low_of_day, the hour bar's
high on the two hour arms — the arm's frame by construction). RISK_PCT is the FILL DAY's: 0.01 before
the 2026-10-03 go to 2% (docs/setups/safeguards.md 2026-10-03), `constants.RISK_PCT` from then;
`sizing_risk_pct` and `sizing_regime_mult` are stored beside it ("never re-framed"). Regime sizing is
ACTING (safeguards.md: live since 2026-07-26), so the row's `regime` label drives the multiplier.
LIMITS, as H10 states them: share rounding, the zero-share reject, the per-strategy / drawdown sizing
multipliers, breakers, position caps and the daily loss limit are not modelled. `capped_dollar_r()`
scores ANY arm row the same way from its stored `realized_r`, `entry_price`, `stop_price`, `orb_high`,
`regime` and `fill_day` — the twelve old arms' rows are frozen and carry no capped column.

THE FILL-VS-TRIGGER COLUMNS (PENG 2026-10-07, #414: the stop-buy triggered at the ORB high $69.20,
FILLED at $72.21 (+4.3%), the stop stayed at $62.20, so the risk actually carried was $100.10 against
a $76.32 budget — +31%). On the `fill_facts` row only, from the LIVE fill and the static `hard_stop`:
`fill_vs_trigger_pct`, `fill_slippage_dollars`, `real_risk_dollars`, `risk_budget_dollars`,
`real_risk_vs_budget`, `real_risk_vs_trigger_risk`. NULL (never substituted) when the trade row lacks
an input. `risk_dollars` can be overwritten by composite sizing (db.py's #571 note), so
`real_risk_vs_budget` is informational; `fill_vs_trigger_pct` is pure price.

WHY A SIBLING MODULE, NOT MORE `ARMS` IN live_fill_counterfactuals.py. That file (with rule_eras,
constants and exit_logic) is hash-pinned by the #705 v2 Consolidation-Breakout freeze
(`docs/analysis/cb_2017_21_rerun_v2_prereg_2026-10-25.md` §8, sha256 6bdb44b9…); editing it would make
the frozen #705 v2 read (run 2026-10-26, ed395838) irreproducible — its freeze re-check refuses on a
changed pin. This module imports and calls its pure walk (`walk_arm`) and helpers, writes into the
SAME table, and gives its rows the names `db.BOOK_MODULE_ARMS`; `db._COUNTERFACTUAL_FILLS_SQL`
excludes them from the original recorder's own `n_arms` count (without that a fill carrying 10 of its
12 arms plus these would read 12 and strand the still-pending ones for ever).

THE LINE. A passive OBSERVER, exactly like the module it extends: exactly ONE write target
(`mi_live_fill_counterfactuals`, via `insert_live_fill_counterfactual`, plus `mi_audit_log`); never
writes a trade row; never touches the broker; read by no grading / entry / sizing / ordering /
safeguard path; SILENT (no Telegram) while evidence accrues; write-once per (trade_id, arm); a
failure is a counted error + audit row and `run_book_geometry_arms` never raises. NO live bracket,
stop, size or entry moves (#482's line: no live bracket change until full-scope evidence + operator
sign + N>=10 backtest).
"""
from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from typing import Any, Optional

from shared.dates import _ET

from agents.market_intelligence import live_fill_counterfactuals as lfc
from agents.market_intelligence.broker.hour_bar_walk import (  # exec-boundary-ok: pure first-hour walk math, no Alpaca client (the exit_logic precedent) — shared with the shadow tracker's 60-minute lane
    FIRST_HOUR_END,
    FIRST_HOUR_START,
    MIN_HOUR_BARS,
    NO_ENTRY_HOUR,
    REGULAR_CLOSE,
    classify_hour_entry,
    entry_walk,
    first_hour_frame,
    session_close_et,
    stop_limit_buy_price,
)
from agents.market_intelligence.constants import (
    MAX_POSITION_PCT,
    RISK_PCT,
    regime_risk_multiplier,
)
from agents.market_intelligence.db import (
    BOOK_FILL_FACTS_ARM,
    BOOK_MODULE_ARMS,
    _f,
    get_book_arm_fills,
    get_counterfactual_arms_written,
    get_daily_ohlc_range,
    get_ep_alert_admission_stamp,
    get_pool,
    insert_live_fill_counterfactual,
    log_audit_event,
)
from agents.market_intelligence.live_fill_counterfactuals import (
    ARMS,
    BACKFILL_FROM,
    GAP_RETRY_SESSIONS,
    PRIOR_CLOSES_CAL_DAYS,
    ADR_LOOKBACK_CAL_DAYS,
    TARGET_R,
    compute_adr20_pct,
    depth_adr20_from_rows,
    pinned_target,
    walk_arm,
)
from agents.market_intelligence.rule_eras import (
    DEPTH_EXIT_RULE,
    admission_era_as_of,
    exit_era_label,
    exit_rules_as_of,
)

logger = logging.getLogger(__name__)

SETTLE_VERSION = "book_v1"
# FIRST_HOUR_START / FIRST_HOUR_END / MIN_HOUR_BARS / REGULAR_CLOSE / NO_ENTRY_HOUR: broker/hour_bar_walk
# The 2% base risk went live with the 2026-10-03 (Saturday) deploy — docs/setups/safeguards.md
# 2026-10-03. Fills before it were sized at 1%. constants.py is hash-frozen, so the switch date lives here.
RISK_PCT_2PCT_FROM = date(2026, 10, 3)
RISK_PCT_BEFORE_2PCT = 0.01

ENTRY_RULE_LIVE = "live_fill"
ENTRY_RULE_FIRST_HOUR = "first_hour_bar_high"
FILL_FACTS_REASON = "fill_facts_only"

# (arm, kind, stop_rule, harvest_rule, trail_rule, follows_live_rule) — the lfc.ARMS tuple shape, so
# lfc._base_fields takes them unchanged. All three follow the live rule (live_replay's levels): they
# are "the live ladder" with the entry, the stop, or both moved.
BOOK_ARMS: tuple[tuple[str, str, str, str, str, bool], ...] = (
    ("entry_first_hour_bar", "entry", "first_hour_2r", "live_ladder", "sma", True),
    ("stop_low_of_day", "stop", "low_of_day", "live_ladder", "sma", True),
    ("book_first_hour_low_of_day", "book", "low_of_day", "live_ladder", "sma", True),
)
# The per-fill facts row: follows_live_rule False and kept OUT of BOOK_ARMS, so the #631 per-fill level
# pin (`pinned` below) can never read a fill's levels from it.
FILL_FACTS_ARM: tuple[str, str, str, str, Optional[str], bool] = (
    BOOK_FILL_FACTS_ARM, "fill_facts", "live", "none", None, False)
_HOUR_ENTRY_ARMS = frozenset({"entry_first_hour_bar", "book_first_hour_low_of_day"})
ERROR_EVENT = "book_geometry_arm_error"


# ── Pure compute (fixture-testable, no IO) ─────────────────────────────────────────────


def risk_pct_at(fill_day: date) -> float:
    """The base risk the sizing path used on `fill_day`: 1% before the 2026-10-03 go to 2%."""
    return RISK_PCT if fill_day >= RISK_PCT_2PCT_FROM else RISK_PCT_BEFORE_2PCT


def capped_risk_fraction(fill: Optional[float], stop: Optional[float], trigger: Optional[float],
                         mult: float, risk_pct: float) -> Optional[tuple[float, bool]]:
    """(risk placed in units of one full R, cap_binding) — sized off the TRIGGER, result off the FILL
    (module docstring). None when the frame is invalid (fill or trigger at/below the stop)."""
    if fill is None or stop is None or trigger is None or trigger <= 0 or risk_pct <= 0:
        return None
    if fill - stop <= 0 or trigger - stop <= 0:
        return None
    budget_term = mult * (fill - stop) / (trigger - stop)
    cap_term = MAX_POSITION_PCT * (fill - stop) / (trigger * risk_pct)
    return min(budget_term, cap_term), cap_term < budget_term


def capped_dollar_scoring(fill: Optional[float], stop: Optional[float], trigger: Optional[float],
                          regime: Optional[str], realized_r: Optional[float], fill_day: date) -> dict[str, Any]:
    """The five capped-dollar columns for one arm. All NULL without a valid fill/stop/trigger; the
    sizing columns are written whenever the frame is valid, `realized_r_capped` only on a settled R."""
    keys = ("sizing_risk_pct", "sizing_regime_mult", "risk_frac_capped", "cap_binding", "realized_r_capped")
    out: dict[str, Any] = {k: None for k in keys}
    mult, rp = regime_risk_multiplier(regime), risk_pct_at(fill_day)
    got = capped_risk_fraction(fill, stop, trigger, mult, rp)
    if got is None:
        return out
    frac, binding = got
    out.update(sizing_risk_pct=rp, sizing_regime_mult=mult, risk_frac_capped=frac, cap_binding=binding,
               realized_r_capped=(realized_r * frac) if realized_r is not None else None)
    return out


def capped_dollar_r(row: dict) -> Optional[float]:
    """H10's capped-dollar R-equivalent for ANY stored arm row (old or new): realized_r × the risk the
    sizing path would have placed, from the row's own entry_price (the fill), stop_price, orb_high (the
    trigger), regime and fill_day. None when an input is missing."""
    fill_day = row.get("fill_day")
    if isinstance(fill_day, str):
        fill_day = date.fromisoformat(fill_day[:10])
    realized_r = _f(row.get("realized_r"))
    if realized_r is None or not isinstance(fill_day, date):
        return None
    got = capped_risk_fraction(_f(row.get("entry_price")), _f(row.get("stop_price")), _f(row.get("orb_high")),
                               regime_risk_multiplier(row.get("regime")), risk_pct_at(fill_day))
    return None if got is None else realized_r * got[0]


def fill_vs_trigger(trade: dict) -> dict[str, Optional[float]]:
    """The live fill against its own trigger (the ORB high): slippage, and what it did to the risk
    the position really carried. Every figure NULL when the trade row lacks an input."""
    entry, trigger = _f(trade.get("entry_price")), _f(trade.get("orb_high"))
    stop, shares = _f(trade.get("hard_stop")), _f(trade.get("entry_shares"))
    budget = _f(trade.get("risk_dollars"))
    out: dict[str, Optional[float]] = {
        "fill_vs_trigger_pct": None, "fill_slippage_dollars": None, "real_risk_dollars": None,
        "risk_budget_dollars": budget if (budget and budget > 0) else None,
        "real_risk_vs_budget": None, "real_risk_vs_trigger_risk": None}
    if entry is None or trigger is None or trigger <= 0:
        return out
    out["fill_vs_trigger_pct"] = (entry - trigger) / trigger * 100.0
    if shares:
        out["fill_slippage_dollars"] = shares * (entry - trigger)
    if stop is not None and entry > stop:
        if shares:
            out["real_risk_dollars"] = shares * (entry - stop)
            if out["risk_budget_dollars"]:
                out["real_risk_vs_budget"] = out["real_risk_dollars"] / out["risk_budget_dollars"]
        if trigger > stop:
            out["real_risk_vs_trigger_risk"] = (entry - stop) / (trigger - stop)
    return out


# stop_limit_buy_price / entry_walk / first_hour_frame / session_close_et / classify_hour_entry:
# broker/hour_bar_walk.py (re-exported above; the tests pin parity through this module's names).


def low_of_day_before(bars: list[dict], fill_idx: int) -> Optional[float]:
    """The lowest 1-minute low of the session strictly BEFORE the fill bar (None = no earlier bar)."""
    lows = [b["l"] for b in bars[:fill_idx] if b.get("l") is not None]
    return min(lows) if lows else None


def _et_bars(day0_bars: list[dict]) -> list[dict]:
    """The stored bars with `m` normalised to ET (the walks compare wall-clock times)."""
    out = []
    for b in day0_bars:
        m = b["m"].astimezone(_ET) if isinstance(b["m"], datetime) else b["m"]
        out.append({**b, "m": m})
    return out


# ── Orchestration (DB reads; writes only mi_live_fill_counterfactuals + audit) ─────────


_OUTCOME_KEY = {"settled": "settled", "abstain": "abstained", "unscoreable": "unscoreable", "horizon": "horizon"}


async def _write(fields: dict, out: dict, label: str) -> bool:
    changed = await lfc.write_replay_row(
        fields, out, label,
        upsert=insert_live_fill_counterfactual,
        error_event=ERROR_EVENT,
        outcome_key=lambda f: (
            "fill_facts" if f.get("arm") == BOOK_FILL_FACTS_ARM else _OUTCOME_KEY[f["outcome"]]),
    )
    # counted only once the row is really in (a failed or conflicting write is not a no-entry)
    if changed and fields.get("outcome") == "unscoreable" and str(fields.get("final_reason") or "").startswith("no_entry:"):
        out["no_entry"] += 1
    return changed


def _count_pending(out: dict, res: dict) -> None:
    out["pending"] += 1
    reason = str(res.get("reason") or "")
    if res.get("pending_at") is None or reason.startswith("depth_next_open"):
        out["pending_open_walk"] += 1        # the walk is still open: it settles as sessions pass
    else:
        out["pending_data_gap"] += 1         # a stored-data hole: retried, abstained once stale


def _arm_fields(trade: dict, arm: tuple, *, fill_day: date, inputs: dict, era: dict,
                stamp: Optional[dict], last_session: date, target_price: Optional[float],
                target_r: Optional[float], breakeven_arm_r: Optional[float]) -> dict:
    fields = lfc._base_fields(trade, arm, fill_day=fill_day, inputs=inputs, era=era, stamp=stamp,
                              settled_session=last_session, target_price=target_price,
                              target_r=target_r, breakeven_arm_r=breakeven_arm_r)
    fields["settle_version"] = SETTLE_VERSION
    fields["entry_rule"] = ENTRY_RULE_FIRST_HOUR if arm[0] in _HOUR_ENTRY_ARMS else ENTRY_RULE_LIVE
    return fields


def _finish(fields: dict, res: dict, *, entry: Optional[float], stop: Optional[float],
            trigger: Optional[float], adr_dollar: Optional[float], outcome: str,
            day0_count: Optional[int], fill_day: date) -> dict:
    fields.update(lfc._outcome_fields(res, entry=entry or 0.0, stop=stop, adr_dollar=adr_dollar,
                                      outcome=outcome, day0_bar_count=day0_count))
    fields.update(capped_dollar_scoring(entry if stop is not None else None, stop, trigger,
                                        fields.get("regime"), fields.get("realized_r"), fill_day))
    return fields


async def _record_one_fill(conn, trade: dict, last_session: date, out: dict, overrides: dict) -> None:
    trade_id = int(trade["id"])
    ticker = trade["ticker"]
    label = f"{ticker} trade {trade_id}"
    written = await get_counterfactual_arms_written(conn, trade_id)
    todo = [a for a in BOOK_ARMS if a[0] not in written]
    facts_todo = BOOK_FILL_FACTS_ARM not in written
    if not todo and not facts_todo:
        return
    out["fills_considered"] += 1
    out["arms_considered"] += len(todo) + int(facts_todo)

    filled_at = trade.get("filled_at")
    if not isinstance(filled_at, datetime):
        raise ValueError("filled_at missing on a filled row")
    fill_day = filled_at.astimezone(_ET).date()
    alert_date = trade["alert_date"]
    entry = _f(trade.get("entry_price"))
    orb_high, orb_low = _f(trade.get("orb_high")), _f(trade.get("orb_low"))
    live_stop = _f(trade.get("hard_stop"))

    # The era comes from THE ROW exactly as the original recorder reads it (#687), never a date.
    _sig, _rule = trade.get("signal_type"), trade.get("exit_rule")
    era = {"exit_era": exit_era_label(alert_date, _sig, _rule),
           "exit_rules": exit_rules_as_of(alert_date, _sig, _rule),
           "admission_era": admission_era_as_of(alert_date)}
    rules = era["exit_rules"]
    is_depth = _rule == DEPTH_EXIT_RULE
    stamp = await get_ep_alert_admission_stamp(conn, ticker, alert_date)

    # The live rule the follows-live arms walk: a fill's levels are FIXED by its own first
    # follows-live row (#631) — read from the original recorder's rows first, then this module's.
    live_target_r = lfc.resolve_target_r(_sig, overrides, TARGET_R)
    live_be_r = lfc.resolve_breakeven_arm_r(_sig, overrides)
    pinned = next((written[a[0]] for a in (*ARMS, *BOOK_ARMS)
                   if a[5] and a[0] in written and written[a[0]].get("target_r") is not None), None)
    if pinned is not None:
        live_target_r = float(pinned["target_r"])
        _be = pinned.get("breakeven_arm_r")
        live_be_r = float(_be) if _be is not None else None

    pre = await get_daily_ohlc_range(conn, ticker, alert_date - timedelta(days=ADR_LOOKBACK_CAL_DAYS),
                                     alert_date - timedelta(days=1))
    adr20_pct, adr20_n = compute_adr20_pct(pre)
    depth_adr = depth_adr20_from_rows(pre) if is_depth else None
    prior_cut = alert_date - timedelta(days=PRIOR_CLOSES_CAL_DAYS)
    prior_closes = [float(r["close"]) for r in pre
                    if r.get("close") is not None and r["trade_date"] >= prior_cut]
    live_inputs = {"entry": entry, "orb_high": orb_high, "orb_low": orb_low, "live_stop": live_stop,
                   "adr20_pct": adr20_pct, "adr20_n": adr20_n,
                   "adr_dollar": (adr20_pct / 100.0 * entry) if (adr20_pct is not None and entry) else None}

    # ── the per-fill facts row: written on the fill's FIRST night, whatever the walks are doing ──
    if facts_todo:
        try:
            fields = _arm_fields(trade, FILL_FACTS_ARM, fill_day=fill_day, inputs=live_inputs, era=era,
                                 stamp=stamp, last_session=last_session, target_price=None,
                                 target_r=None, breakeven_arm_r=None)
            fields.update(fill_vs_trigger(trade))
            fields.update(lfc._outcome_fields({"reason": FILL_FACTS_REASON}, entry=entry or 0.0, stop=None,
                                              adr_dollar=live_inputs["adr_dollar"], outcome="unscoreable",
                                              day0_bar_count=None))
            await _write(fields, out, f"{label} {BOOK_FILL_FACTS_ARM}")
        except Exception as e:  # loud-ok: counted + audited; the walked arms below still run
            out["errors"] += 1
            await log_audit_event(ERROR_EVENT, f"{label} arm {BOOK_FILL_FACTS_ARM}: {type(e).__name__}: {e}")
    if not todo:
        return

    missing = [k for k in ("entry", "orb_high", "orb_low", "live_stop") if live_inputs[k] is None]
    if missing or live_stop >= entry or lfc.orb_r_frame(entry, orb_low) is None:   # the original recorder's guard, leg for leg
        reason = f"missing_inputs:{','.join(missing) or 'invalid_frame'}"
        for arm in todo:
            fields = _arm_fields(trade, arm, fill_day=fill_day, inputs=live_inputs, era=era, stamp=stamp,
                                 last_session=last_session, target_price=None, target_r=live_target_r,
                                 breakeven_arm_r=live_be_r)
            _finish(fields, {"reason": reason}, entry=entry, stop=None, trigger=None,
                    adr_dollar=live_inputs["adr_dollar"], outcome="unscoreable", day0_count=None,
                    fill_day=fill_day)
            await _write(fields, out, f"{label} {arm[0]}")
        return

    day0_raw, fill_idx = await lfc._day0_bars(conn, ticker, fill_day, filled_at)
    bars = _et_bars(day0_raw) if day0_raw else None   # (None, None) = the session or the fill minute is not stored
    sessions = await lfc._assemble_sessions(conn, ticker, fill_day, last_session)

    hour: Optional[dict] = None
    if bars is not None and any(a[0] in _HOUR_ENTRY_ARMS for a in todo):
        close_et = session_close_et(fill_day)
        hour = classify_hour_entry(bars, close_et)
        if hour["kind"] == "needs_daily_high":
            d0 = await get_daily_ohlc_range(conn, ticker, fill_day, fill_day)
            d0_high = _f(d0[0].get("high_price")) if d0 else None
            if d0_high is None:
                hour = {"kind": "pending", "high": hour["high"], "low": hour["low"],
                        "reason": f"{hour['walk_reason']}:no_stored_day0_daily_bar"}
            else:
                hour = classify_hour_entry(bars, close_et, d0_high)

    for arm in todo:
        name = arm[0]
        try:
            inputs = dict(live_inputs)
            arm_entry: Optional[float] = entry
            trigger: Optional[float] = orb_high
            stop: Optional[float] = None
            target: Optional[float] = None
            r_frame = entry - orb_low
            entry_minute: Optional[str] = None
            fill_i = fill_idx
            fail: Optional[tuple[str, str]] = None    # (outcome, reason): written WITHOUT a walk
            gap: Optional[str] = None                 # a data-gap reason: pending, abstained when stale

            if bars is not None and name == "stop_low_of_day":
                stop = low_of_day_before(bars, fill_idx)
                if stop is None:
                    fail = ("unscoreable", "no_bars_before_fill")
                elif stop >= entry:
                    fail = ("unscoreable", f"lod_at_or_above_entry:{stop}")
                target = pinned_target(entry, orb_low, live_target_r)
            elif bars is not None:    # the two hour-entry arms
                # orb_high / orb_low on these rows are the HOUR bar's (the arm's own frame); NULL
                # when the hour bar itself is not trusted (a thin first hour) — never the 1-min ORB
                inputs.update(orb_high=hour.get("high"), orb_low=hour.get("low"))
                trigger = hour.get("high")
                if hour["kind"] != "filled":
                    arm_entry = None                  # no entry happened (or is not known yet)
                    inputs["entry"] = None
                    inputs["adr_dollar"] = None
                    if hour["kind"] == "no_entry":
                        fail = ("unscoreable", hour["reason"])
                    else:
                        gap = hour["reason"]
                else:
                    arm_entry = hour["px"]
                    fill_i = next(i for i, b in enumerate(bars) if b["m"] == hour["minute"])
                    entry_minute = hour["minute"].strftime("%H:%M")
                    r_frame = arm_entry - hour["low"]
                    inputs["entry"] = arm_entry
                    inputs["adr_dollar"] = (adr20_pct / 100.0 * arm_entry) if adr20_pct is not None else None
                    if name == "entry_first_hour_bar":
                        stop = 2 * hour["low"] - hour["high"]
                        if stop <= 0:
                            fail = ("unscoreable", f"first_hour_2r_stop_nonpositive:{stop:.2f}")
                    else:                             # book_first_hour_low_of_day
                        stop = low_of_day_before(bars, fill_i)
                        if stop is None:
                            fail = ("unscoreable", "no_bars_before_fill")
                        elif stop >= arm_entry:
                            fail = ("unscoreable", f"lod_at_or_above_entry:{stop}")
                    if fail is None:
                        target = pinned_target(arm_entry, hour["low"], live_target_r)

            fields = _arm_fields(trade, arm, fill_day=fill_day, inputs=inputs, era=era, stamp=stamp,
                                 last_session=last_session, target_price=target, target_r=live_target_r,
                                 breakeven_arm_r=live_be_r)
            fields["entry_minute"] = entry_minute

            if fail is not None:
                outcome, reason = fail
                _finish(fields, {"reason": reason}, entry=arm_entry, stop=None, trigger=None,
                        adr_dollar=inputs["adr_dollar"], outcome=outcome, day0_count=None, fill_day=fill_day)
                await _write(fields, out, f"{label} {name}")
                continue

            if bars is None:
                # the session or the fill minute is not stored: pending, retried nightly, abstain once
                # the gap is GAP_RETRY_SESSIONS old (the original recorder's rule)
                res = {"status": "pending", "reason": "no_day0_minute_bars", "pending_at": fill_day}
            elif gap is not None:
                # a thin first hour, or post-10:30 holes the daily bar could not decide: the same rule
                res = {"status": "pending", "reason": gap, "pending_at": fill_day}
            else:
                res = walk_arm(entry=arm_entry, stop=stop, target=target, day0_bars=bars, fill_idx=fill_i,
                               sessions=sessions, prior_closes=prior_closes, harvest="live_ladder",
                               fill_day=fill_day,
                               breakeven_at_partial=bool(rules["breakeven_at_partial"]),
                               trail_prior_closes=bool(rules["trail_prior_closes"]),
                               ladder_partial=bool(rules["ladder_partial"]),
                               breakeven_at_r=live_be_r, r_frame_ps=r_frame,
                               trail_mode="sma", depth_exit=is_depth,
                               depth_adr20_pct=depth_adr if is_depth else None)
            status = res["status"]
            if status == "pending":
                gap_at = res.get("pending_at")
                stale = (gap_at is not None and len(lfc._trading_days(gap_at + timedelta(days=1), last_session))
                         >= GAP_RETRY_SESSIONS)
                if not stale:
                    _count_pending(out, res)
                    continue
                status = "abstain"          # the gap never closed: recorded, counted, never leapt
            walked = bars is not None and gap is None
            day0_count = (len(bars) - fill_i) if (walked and fill_i is not None) else (0 if bars is None else None)
            _finish(fields, res, entry=arm_entry, stop=stop, trigger=trigger, adr_dollar=inputs["adr_dollar"],
                    outcome=status, day0_count=day0_count, fill_day=fill_day)
            await _write(fields, out, f"{label} {name}")
        except Exception as e:  # loud-ok: one arm's failure is counted; the others and the live trade proceed
            out["errors"] += 1
            await log_audit_event(ERROR_EVENT,
                                  f"{label} arm {name}: {type(e).__name__}: {e}")


async def run_book_geometry_arms(today: Optional[date] = None, *,
                                 now_et: Optional[datetime] = None) -> dict[str, int]:
    """Nightly entry point (rides the 18:04 ET `live_fill_counterfactuals` job, after the original
    recorder). NEVER raises: every failure is a counted error + an mi_audit_log row."""
    now = now_et or datetime.now(_ET)
    today = today or now.date()
    out: dict[str, int] = {"population": 0, "fills_considered": 0, "arms_considered": 0,
                           "written": 0, "fill_facts": 0, "settled": 0, "abstained": 0, "unscoreable": 0,
                           "horizon": 0, "pending": 0, "pending_open_walk": 0, "pending_data_gap": 0,
                           "errors": 0, "no_entry": 0}
    try:
        last_session = lfc.last_settled_session(today, now)
        fills = await get_book_arm_fills(BACKFILL_FROM, BOOK_MODULE_ARMS)
    except Exception as e:  # loud-ok: the run reports and ends; nothing live depends on it
        out["errors"] += 1
        await log_audit_event(ERROR_EVENT, f"fill query failed: {e}")
        return out
    out["population"] = len(fills)
    if fills:
        try:
            pool = await get_pool()
            async with pool.acquire() as conn:
                overrides = await lfc.load_exit_overrides(conn)
                for trade in fills:
                    try:
                        await _record_one_fill(conn, trade, last_session, out, overrides)
                    except Exception as e:  # loud-ok: per-fill isolation; counted + audited
                        out["errors"] += 1
                        await log_audit_event(
                            ERROR_EVENT,
                            f"{trade.get('ticker')} trade {trade.get('id')}: {type(e).__name__}: {e}")
        except Exception as e:  # loud-ok: pool-level failure; counted + audited
            out["errors"] += 1
            await log_audit_event(ERROR_EVENT, f"run failed: {e}")
    await log_audit_event("book_geometry_arms_recorded", audit_summary(out))
    return out


def audit_summary(out: dict) -> str:
    """The run's one audit line (also what the 18:04 job logs). Every walked arm a fill still lacks is
    either written tonight, counted pending here (split open walk / data gap), or counted an error."""
    return (f"{out['population']} fill(s) with book rows to write, {out['arms_considered']} row(s) "
            f"considered: {out['written']} written ({out['fill_facts']} fill-facts, {out['settled']} settled, "
            f"{out['abstained']} abstained, {out['unscoreable']} unscoreable of which "
            f"{out['no_entry']} no-entry, {out['horizon']} at horizon), {out['pending']} pending "
            f"({out['pending_open_walk']} open walk, {out['pending_data_gap']} data gap), "
            f"{out['errors']} error(s)")
