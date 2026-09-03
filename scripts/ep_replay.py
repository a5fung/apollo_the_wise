"""EP raw-bar replay harness — re-score / re-admit / reconstruct outcomes over STORED bars
under an EXPLICIT rule-set, so any past day can be read as if a chosen stack had been live.

WHY (operator ruling, 2026-08-30 / #482 fork option b): the live stack changes faster than
trades accrue — every era-gated cohort is too small, every pooled cohort is era-mixed. The
operator ruled the way out: *"just use raw data to run our analysis given we have minute bars
stored, that is the path we should go."* This harness makes that replay routine and REUSABLE
(scripts/, not scripts/probes/).

FIDELITY CONTRACT (what makes this measure anything — the #482 lesson, where every positive
number turned out to be a daily-bar replay, not a real fill):
  - LIVE CODE PATHS, never re-implementations, wherever a pure function exists:
      validate_orb_entry            (backtester/filters.py — the single ORB admission rule)
      stop_limit_buy_price          (broker/order_manager.py — the entry limit cap)
      profit_target_r_per_share     (broker/order_manager.py — the +2R target's R frame)
      seed_exit_state / apply_daily_exit_step  (broker/exit_logic.py — THE canonical ladder)
      _score_ep + ep_rubric resolvers          (the live scorer, both weight tables)
    The only harness-side mechanics are BROKER microstructure the live modules delegate to
    Alpaca (stop-buy trigger/fill, resting-stop fill, gap-through at the open) — each is
    validated per-trade against mi_live_trades real fills by `validate` before anyone quotes
    a replay number.
  - RULE-SET IS AN EXPLICIT INPUT. `get_ruleset(None)` raises. Every output row carries the
    rule-set name. `ruleset_as_of(date)` composes the stack that was live on a date from the
    dated switch table below — era-mixing by accident is impossible.
  - ABSTAIN, NEVER FABRICATE. Missing 9:30 bar -> no ORB -> abstain. No minute coverage of
    the entry window and no cross found -> abstain (cannot prove no-entry). Stop and target
    inside the same bar/day with no finer bar to order them -> abstain. Missing daily bar ->
    session abstained and counted. Abstain rate is a first-class output.
  - Prod is READ-ONLY. This module only reads TSV captures under scripts/ep_replay_data/
    (see the _pull*.sql files there for the exact SELECTs) and writes result TSVs next to
    them. No live table is ever written (THE LINE: measurement only).

KNOWN DEVIATIONS from live behaviour (each stated, none silent):
  - +2R partial books AT the target price (today's resting-limit semantics). Era-B real
    fills were poll-time market fills (FIGS -0.87R / PLTR +0.9R class); validate reports the
    per-trade delta rather than modelling the poll.
  - 🔴 The Day 3-5 ladder partial: THE HARNESS TAKES IT, LIVE DOES NOT (corrected 2026-09-02;
    this line previously said live "fills near it", which was wrong). live_tracker.py:1076 passes
    `skip_partial_decision=bool(PROFIT_TRIGGER_R)` — and PROFIT_TRIGGER_R has been set since the
    +2R partial landed 08-01 — so live SKIPS the day-3/5 partial decision entirely. Measured
    blast radius: it moves 14 of 267 campaigns and flips CORT and ATRO from small wins to small
    losses. No verdict in #545 turned on it, but a replay that books a partial live stands down
    is optimistic by construction on every runner, which is exactly the direction that flatters
    a harvest finding.
  - Same-day-after-partial the resting stop stays at the ORIGINAL stop (breakeven_at_broker
    default-OFF behaviour, confirmed by FIGS 08-07); breakeven enters via the ladder's
    effective stop from the NEXT session — matches CRWD 08-28's breakeven fill.
  - Re-entry after a same-day stop-out (entry_attempt > 1) is NOT replayed — first attempts
    only. The 6 attempt-2 trades are excluded from agreement and counted.
  - Portfolio-level state is NOT replayed: slot ranking / max-positions / loss limits /
    breakers need book state that per-campaign replay cannot know. This harness measures
    per-campaign selection + geometry, not portfolio interaction.
  - The judge/tier layer (LLM) and post-grade filters needing live news are NOT re-run;
    stored grades are treated as stored facts. Re-scoring is the DETERMINISTIC score+bar.

Usage (all read from scripts/ep_replay_data/ captures):
    python scripts/ep_replay.py rulesets
    python scripts/ep_replay.py validate                # era-matched replay vs real trades
    python scripts/ep_replay.py score                   # re-score vs stored ep_score
    python scripts/ep_replay.py replay --ruleset current [--out name.tsv]
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from shared.dates import _ET as _SHARED_ET  # noqa: E402
from agents.market_intelligence.backtester.filters import validate_orb_entry  # noqa: E402
from agents.market_intelligence.broker.exit_logic import (  # noqa: E402
    apply_daily_exit_step,
    seed_exit_state,
)
from agents.market_intelligence.broker.order_manager import (  # noqa: E402
    profit_target_r_per_share,
    stop_limit_buy_price,
)
from agents.market_intelligence.ep_detector import _score_ep  # noqa: E402
from agents.market_intelligence.ep_rubric import (  # noqa: E402
    resolve_ep_bar,
    resolve_score_weights,
)

_ET = _SHARED_ET  # the CANONICAL zone (shared/dates.py) — never a second one here
DATA = REPO / "scripts" / "ep_replay_data"

# Last daily bar treated as settled. 2026-09-01 exists in the capture but is the capture
# day itself; a partial day must never settle an exit.
LAST_SETTLED = date(2026, 8, 31)


class RuleSetRequired(ValueError):
    """Raised when a replay is attempted without naming a rule-set."""


# ── Rule-sets ────────────────────────────────────────────────────────────────────────
# Dated switch table — provenance for every line:
#   score separation + rescale   2026-08-22  (#533, operator-signed; magna53_ep.md change log)
#   protective stop entry−2R     2026-08-16  (operator-signed; order_manager ~L481)
#   +2R intraday partial live    2026-08-01  (#508, constants.PROFIT_TRIGGER_R)
#   trail uses stock's own MA    2026-08-08  (#548, prior_closes)
#   10:00 ET unfilled-cancel     era B/C     (CLAUDE.md ORB window; era-A fills as late as
#                                             11:35 prove no cancel then — KURA 04-17)
SEP_SCORE_DATE = date(2026, 8, 22)
STOP_2R_DATE = date(2026, 8, 16)
PARTIAL_LIVE_DATE = date(2026, 8, 1)
TRAIL_PRIOR_CLOSES_DATE = date(2026, 8, 8)
# #548 ships the partial's breakeven move AT the broker (stop replaced at entry when the
# partial fires). Validated against real fills: FIGS 08-07 stopped at the ORIGINAL stop
# after its partial (pre-#548), ETON 08-14 and CRWD 08-28 stopped at BREAKEVEN (post).
BREAKEVEN_AT_PARTIAL_DATE = date(2026, 8, 8)


@dataclass(frozen=True)
class RuleSet:
    name: str
    score_separation: bool          # True -> SCORE_WEIGHTS + bar 65; False -> legacy + per-regime bar
    stop_mode: str                  # "orb_low" | "entry_minus_2r"
    intraday_partial_r: float | None  # None = no +2R partial (era A); 2.0 since 2026-08-01
    trail_prior_closes: bool        # #548: trail sees the stock's own closes
    entry_cancel: time | None       # unfilled entry cancelled at this ET time (None = end of day)
    breakeven_at_partial: bool = False  # #548: partial moves the resting stop to entry at once

    def stop_price(self, orb_high: float, orb_low: float) -> float:
        """The protective stop this rule-set places. Formula provenance:
        orb_low        — the original OTO bracket stop (CLAUDE.md Paper Trading).
        entry_minus_2r — order_manager ~L498: stop = 2*orb_low − orb_high (R = orb range;
                         sizing self-halves through the doubled distance).
        Validated per-trade against mi_live_trades.hard_stop by `validate`."""
        if self.stop_mode == "orb_low":
            return orb_low
        if self.stop_mode == "entry_minus_2r":
            return 2 * orb_low - orb_high
        raise ValueError(f"unknown stop_mode {self.stop_mode!r}")


RULESETS: dict[str, RuleSet] = {
    "era_a": RuleSet("era_a", False, "orb_low", None, False, None),
    "era_b": RuleSet("era_b", False, "orb_low", 2.0, False, time(10, 0)),
    "era_c": RuleSet("era_c", True, "entry_minus_2r", 2.0, True, time(10, 0), True),
}
RULESETS["current"] = RULESETS["era_c"]


def get_ruleset(name: str | None) -> RuleSet:
    if not name:
        raise RuleSetRequired(
            "a rule-set is required — pass one of "
            f"{sorted(RULESETS)} or use ruleset_as_of(<date>); refusing to guess")
    try:
        return RULESETS[name]
    except KeyError:
        raise RuleSetRequired(f"unknown rule-set {name!r}; known: {sorted(RULESETS)}") from None


def ruleset_as_of(d: date) -> RuleSet:
    """The stack that was live on date d, composed from the dated switch table.
    NB: the score side of pre-2026-08-22 stacks is approximate — components deleted on
    08-22 (neglect, prior-momentum) no longer exist in the code, so old scores are stored
    facts, not re-derivable. `score` measures exactly how far that reaches."""
    return RuleSet(
        name=f"as_of_{d.isoformat()}",
        score_separation=d >= SEP_SCORE_DATE,
        stop_mode="entry_minus_2r" if d >= STOP_2R_DATE else "orb_low",
        intraday_partial_r=2.0 if d >= PARTIAL_LIVE_DATE else None,
        trail_prior_closes=d >= TRAIL_PRIOR_CLOSES_DATE,
        entry_cancel=time(10, 0) if d >= PARTIAL_LIVE_DATE else None,
        breakeven_at_partial=d >= BREAKEVEN_AT_PARTIAL_DATE,
    )


# ── Capture readers (psql -A format: header row, | delimiter, "(N rows)" trailer) ────

def _f(v):
    if v in (None, "", "\\N"):
        return None
    try:
        return float(v)
    except ValueError:
        return None


def read_sections(path: Path) -> dict[str, list[dict]]:
    sections: dict[str, list[str]] = {}
    cur = None
    for line in path.read_text().splitlines():
        if line.startswith("=== "):
            cur = line.strip("= ").strip()
            sections[cur] = []
        elif cur is not None:
            sections[cur].append(line)
    out: dict[str, list[dict]] = {}
    for name, lines in sections.items():
        lines = [l for l in lines if l and not (l.startswith("(") and l.endswith("rows)"))]
        if not lines:
            out[name] = []
            continue
        hdr = lines[0].split("|")
        out[name] = [dict(zip(hdr, p)) for l in lines[1:]
                     if len(p := l.split("|")) == len(hdr)]
    return out


def load_minutes() -> dict[tuple[str, date], list[dict]]:
    """(ticker, ET day) -> ordered RTH 1-min bars {'m': ET datetime, 'o','h','l','c'}."""
    import gzip
    by: dict[tuple[str, date], list[dict]] = {}
    with gzip.open(DATA / "_pull4_min.tsv.gz", "rt") as fh:
        for line in fh:
            p = line.rstrip("\n").split("|")
            if len(p) != 7 or p[0] == "ticker" or p[0].startswith("==="):
                continue
            try:
                dt = datetime.strptime(p[1], "%Y-%m-%d %H:%M").replace(tzinfo=_ET)
            except ValueError:
                continue
            by.setdefault((p[0], dt.date()), []).append(
                {"m": dt, "o": float(p[2]), "h": float(p[3]),
                 "l": float(p[4]), "c": float(p[5])})
    for bars in by.values():
        bars.sort(key=lambda b: b["m"])
    return by


def load_daily() -> dict[str, dict[date, dict]]:
    out: dict[str, dict[date, dict]] = {}
    for r in read_sections(DATA / "_pull2_out.txt")["DAILY"]:
        d = date.fromisoformat(r["trade_date"])
        out.setdefault(r["ticker"], {})[d] = {
            "o": _f(r["open_price"]), "h": _f(r["high_price"]),
            "l": _f(r["low_price"]), "c": _f(r["close"]), "v": _f(r["volume"])}
    return out


# ── Entry reconstruction (broker microstructure; validated against real fills) ───────

def entry_walk(bars: list[dict], orb_high: float, submit: time,
               cancel: time | None) -> dict:
    """Reconstruct the stop-limit buy (stop = orb_high, limit = stop_limit_buy_price):
    scan minute bars in [submit, cancel); the order triggers when a bar trades >= orb_high.
      bar opens < orb_high, high >= orb_high  -> intra-bar cross, fill AT orb_high
      bar opens in [orb_high, limit]          -> fill at the open
      bar opens above the limit               -> limit-armed; fills at the LIMIT on the
                                                 first later bar with low <= limit
    No cross by cancel: 'no_entry' only when the window has full minute coverage,
    else ABSTAIN — a gap could hide the cross."""
    limit = stop_limit_buy_price(orb_high)
    limit_armed = False
    window = [b for b in bars
              if b["m"].time() >= submit and (cancel is None or b["m"].time() < cancel)]
    for b in window:
        if limit_armed:
            if b["l"] <= limit:
                return {"status": "filled", "px": limit, "minute": b["m"]}
            continue
        if b["o"] >= orb_high:
            if b["o"] <= limit:
                return {"status": "filled", "px": b["o"], "minute": b["m"]}
            limit_armed = True
            if b["l"] <= limit:
                return {"status": "filled", "px": limit, "minute": b["m"]}
        elif b["h"] >= orb_high:
            return {"status": "filled", "px": orb_high, "minute": b["m"]}
    if limit_armed:
        return {"status": "no_entry", "reason": "triggered_above_limit_never_filled"}
    end = cancel if cancel is not None else time(16, 0)
    expected = int((datetime.combine(date.min, end) -
                    datetime.combine(date.min, max(submit, time(9, 30)))).total_seconds() // 60)
    if len(window) < expected:
        return {"status": "abstain",
                "reason": f"entry_window_gaps:{expected - len(window)}_of_{expected}"}
    return {"status": "no_entry", "reason": "never_crossed_orb_high"}


# ── One campaign, end to end ─────────────────────────────────────────────────────────

def walk_campaign(*, ticker: str, alert_date: date, rs: RuleSet,
                  minutes: dict, daily: dict[str, dict[date, dict]],
                  submit: time = time(9, 31),
                  orb_high: float | None = None, orb_low: float | None = None,
                  atr_14: float | None = None,
                  shares: float | None = None, integer_shares: bool = False) -> dict:
    """Replay one (ticker, alert day) campaign under rule-set `rs`, entry to final exit.
    ORB comes from the stored trade row when given (a stored fact of the day), else from
    the 9:30 minute bar. `shares=None` -> normalized fractional sizing (1 risk unit).
    Returns a dict with status/abstain accounting; never fabricates a fill."""
    out = {"ticker": ticker, "alert_date": alert_date, "ruleset": rs.name,
           "status": None, "reason": None, "entered": False, "entry_px": None,
           "stop": None, "target": None, "exits": [], "realized_pnl_per_unit": None,
           "realized_r": None, "partial_fired": False, "final_reason": None,
           "gap_through": False, "day0_missing_minutes": None,
           "sessions_abstained": 0, "flags": []}
    bars0 = minutes.get((ticker, alert_date), [])
    if orb_high is None or orb_low is None:
        orb = next((b for b in bars0 if b["m"].time() == time(9, 30)), None)
        if not orb:
            out.update(status="abstain", reason="no_930_bar_for_orb")
            return out
        orb_high, orb_low = orb["h"], orb["l"]
    ok, skip = validate_orb_entry(orb_high, orb_low, atr_14)
    if not ok:
        out.update(status="no_trade", reason=skip)
        return out
    stop = rs.stop_price(orb_high, orb_low)
    if stop <= 0:
        out.update(status="no_trade", reason="stop_at_or_below_zero")
        return out
    out["stop"] = stop
    if rs.entry_cancel is not None and submit >= time(9, 45):
        # CLAUDE.md ORB window: HIGHs at 9:45-9:59 -> WINDOW_OUT_OF_ORB, no submission
        out.update(status="no_trade", reason="window_out_of_orb")
        return out
    if not bars0:
        out.update(status="abstain", reason="no_day0_minute_bars")
        return out
    rth = {(datetime.combine(alert_date, time(9, 30)) + timedelta(minutes=i)).time()
           for i in range(390)}
    out["day0_missing_minutes"] = len(rth - {b["m"].time() for b in bars0})

    fill = entry_walk(bars0, orb_high, submit, rs.entry_cancel)
    if fill["status"] != "filled":
        out.update(status=fill["status"], reason=fill["reason"])
        return out
    entry_px = fill["px"]
    out.update(entered=True, entry_px=entry_px)

    if shares is None:
        risk_per_share = entry_px - stop
        if risk_per_share <= 0:
            out.update(status="abstain", reason="nonpositive_risk_per_share")
            return out
        shares = 1.0 / risk_per_share      # 1 risk-dollar unit
    risk_denom = shares * (entry_px - stop)

    # +2R target — the live R frame (profit_target_r_per_share: magna53 frames off
    # entry − orb_low, NOT the placed stop; that function owns the rule).
    target = None
    if rs.intraday_partial_r:
        r_ps = profit_target_r_per_share("magna53", entry_px, stop, orb_low)
        if r_ps is not None:
            target = entry_px + rs.intraday_partial_r * r_ps
    out["target"] = target

    remaining = float(shares)
    partial_taken = False
    exits: list[dict] = []

    def book(px: float, qty: float, reason: str, when) -> None:
        exits.append({"time": str(when), "price": px, "reason": reason, "shares": qty,
                      "pnl": (px - entry_px) * qty})

    def take_partial(px: float, when) -> float:
        nonlocal remaining, partial_taken
        qty = float(int(remaining) // 3) if integer_shares else remaining / 3
        if qty <= 0:
            return 0.0
        book(px, qty, "partial_profit", when)
        remaining -= qty
        partial_taken = True
        out["partial_fired"] = True
        return qty

    # ── Day-0 minute walk from the fill bar ──
    cur_stop = stop
    closed = False
    fill_idx = next(i for i, b in enumerate(bars0) if b["m"] == fill["minute"])
    fb = bars0[fill_idx]
    if fb["l"] <= stop:
        if target is not None and fb["h"] >= target:
            # stop AND target both inside the fill bar — order unknowable at 1-min grain
            out.update(status="abstain", reason="day0_fill_bar_stop_and_target")
            return out
        # Provable ordering: entry fills at the first touch >= orb_high; close < stop
        # means the path DESCENDED through the stop after its high-water moment, so the
        # stop fill is post-entry. Close >= stop leaves the order unknowable -> abstain.
        if fb["c"] < stop:
            book(stop, remaining, "stop_hit", fb["m"])
            remaining, closed = 0.0, True
            out["final_reason"] = "stop_hit"
        else:
            out.update(status="abstain", reason="day0_fill_bar_straddles_stop")
            return out
    if not closed and target is not None and fb["h"] >= target and fb["c"] >= stop:
        # Same provability does not exist for target-vs-nothing: a target touch in the
        # fill bar after the cross is orderable (target > orb_high >= any pre-fill price
        # only when orb crossed first) — the touch >= target necessarily post-dates the
        # first >= orb_high touch when target > orb_high, which +2R guarantees.
        if take_partial(target, fb["m"]) and rs.breakeven_at_partial:
            cur_stop = max(cur_stop, entry_px)
    for b in bars0[fill_idx + 1:]:
        if closed:
            break
        hit_stop = b["l"] <= cur_stop
        hit_tgt = (target is not None and not partial_taken and b["h"] >= target)
        if hit_stop and hit_tgt:
            out.update(status="abstain", reason="day0_stop_and_target_same_bar")
            return out
        if hit_stop:
            px = b["o"] if b["o"] < cur_stop else cur_stop
            if px != cur_stop:
                out["gap_through"] = True
            book(px, remaining, "stop_hit", b["m"])
            remaining, closed = 0.0, True
            out["final_reason"] = "stop_hit"
        elif hit_tgt:
            if take_partial(target, b["m"]) and rs.breakeven_at_partial:
                cur_stop = max(cur_stop, entry_px)

    # ── Forward daily walk: the LIVE ladder + the resting-stop overlay ──
    if not closed:
        dbars = daily.get(ticker, {})
        prior = [dbars[d]["c"] for d in sorted(dbars)
                 if d < alert_date and dbars[d]["c"] is not None]
        state = seed_exit_state(
            alert_date=alert_date, entry_price=entry_px, hard_stop=stop,
            remaining_shares=remaining, partial_taken=partial_taken,
            breakeven_active=partial_taken, exits=list(exits))
        resting = cur_stop    # the broker's resting stop; raise-only, per live EOD updates
        d = alert_date
        while not closed:
            d += timedelta(days=1)
            if d > LAST_SETTLED:
                out.update(status="open_at_horizon")
                break
            if d.weekday() >= 5:
                continue
            b = dbars.get(d)
            if not b or b["c"] is None or b["l"] is None or b["h"] is None:
                out["sessions_abstained"] += 1
                continue
            hit_tgt = (target is not None and not state["partial_taken"]
                       and b["h"] >= target)
            if hit_tgt and b["l"] <= resting:
                out.update(status="abstain", reason=f"fwd_stop_and_target_same_day:{d}")
                return out
            if hit_tgt:
                remaining = state["remaining_shares"]
                partial_taken = state["partial_taken"]
                if take_partial(target, d) and rs.breakeven_at_partial:
                    resting = max(resting, entry_px)
                state["remaining_shares"] = remaining
                state["partial_taken"] = True
                state["breakeven_active"] = True
                state["exits"] = list(exits)
            state["hard_stop"] = resting
            step = apply_daily_exit_step(
                state, {"l": b["l"], "c": b["c"]}, d,
                integer_partial_shares=integer_shares,
                prior_closes=(prior if rs.trail_prior_closes else None))
            state.update(remaining_shares=step.new_remaining,
                         partial_taken=step.new_partial_taken,
                         breakeven_active=step.new_breakeven_active,
                         exits=step.new_exits,
                         running_closes=step.new_running_closes)
            if step.closed:
                px, reason = step.close_price, step.close_reason
                if reason == "stop_hit" and b["o"] is not None and b["o"] < px:
                    px = b["o"]           # gap-through honesty: the resting stop fills at the open
                    out["gap_through"] = True
                exits = [e for e in step.new_exits]
                exits[-1] = {**exits[-1], "price": px,
                             "pnl": (px - entry_px) * exits[-1]["shares"]}
                out["final_reason"] = reason
                closed = True
            else:
                exits = list(step.new_exits)
                resting = max(resting, step.effective_stop)
        out["partial_fired"] = any(e["reason"] == "partial_profit" for e in exits)

    out["exits"] = exits
    if closed:
        out["status"] = "settled"
    pnl = sum(e["pnl"] for e in exits)
    out["realized_pnl_per_unit"] = pnl
    if risk_denom > 0 and closed:
        out["realized_r"] = pnl / risk_denom
    return out


# ── Re-score (deterministic slice of the live scorer) ────────────────────────────────

def rescore_alert(alert: dict, rs: RuleSet, adv_20: float | None,
                  prev_close: float | None, regime: str | None,
                  regime_ep_threshold: int | None) -> dict:
    """Re-run _score_ep on the STORED inputs of one alert under rule-set `rs`.
    floatShares is NOT a stored fact -> the score is a BAND [without, with] the float
    bonus; admission abstains when the band straddles the bar. projected_vol_multiple is
    not stored -> the ADV-unknown fallback uses stored rel_volume (flagged)."""
    weights = resolve_score_weights(rs.score_separation)
    mult = (1.2 if regime == "Bull" else 1.0) * (_f(alert.get("confidence_multiplier")) or 1.0)
    adv_dollar = (adv_20 * prev_close) if (adv_20 and prev_close) else None
    common = dict(
        gap_pct=_f(alert["gap_pct"]) or 0.0,
        rel_volume=_f(alert.get("rel_volume")) or 0.0,
        catalyst_quality=alert.get("catalyst_quality") or "",
        regime_multiplier=mult,
        vol_percentile=_f(alert.get("vol_percentile")) if _f(alert.get("vol_percentile")) is not None else 50.0,
        projected_vol_multiple=None,
        in_active_theme=(alert.get("in_active_theme") in ("t", True)),
        adv_dollar=adv_dollar,
        weights=weights,
    )
    lo, _ = _score_ep(profile={"floatShares": 10**12}, **common)   # no float bonus
    hi, _ = _score_ep(profile={"floatShares": 1}, **common)        # float bonus
    bar = resolve_ep_bar(rs.score_separation, regime_ep_threshold or 70)
    if lo >= bar:
        admit = "admit"
    elif hi < bar:
        admit = "reject"
    else:
        admit = "abstain_float_band_straddles_bar"
    return {"score_lo": lo, "score_hi": hi, "bar": bar, "admit": admit,
            "adv_known": adv_dollar is not None}


# ── Phases ───────────────────────────────────────────────────────────────────────────

def _load_common():
    s2 = read_sections(DATA / "_pull2_out.txt")
    s3 = read_sections(DATA / "_pull3_out.txt")
    return s2, s3


def write_tsv(path: Path, rows: list[dict], cols: list[str]) -> None:
    """The ONE pipe-separated writer for every phase of this harness.

    Was three near-identical loops, and they had already drifted: two rendered a None as an
    empty field and phase_score's rendered the literal text "None" — into the very TSVs this
    harness exists to be quotable from. A file whose whole claim is fidelity cannot have three
    spellings of how it writes a missing value.
    """
    with open(path, "w") as fh:
        fh.write("|".join(cols) + "\n")
        for r in rows:
            fh.write("|".join("" if r.get(c) is None else str(r.get(c)) for c in cols) + "\n")


def phase_validate(args) -> None:
    s2, _ = _load_common()
    minutes, daily = load_minutes(), load_daily()
    alerts_by = {(a["ticker"], a["alert_date"]): a for a in s2["ALERTS"]}
    rows, excl = [], {"reentry": 0, "manual_exit": 0, "bad_row": 0}
    for t in s2["TRADES"]:
        ad = date.fromisoformat(t["alert_date"])
        rs = get_ruleset(args.ruleset) if args.ruleset else ruleset_as_of(ad)
        exits_live = json.loads(t["exits_json"] or "[]")
        if int(t["entry_attempt"]) > 1:
            excl["reentry"] += 1
            continue
        if any("manual" in (e.get("reason") or "") for e in exits_live):
            excl["manual_exit"] += 1
            continue
        if not t["filled_at_et"] or not _f(t["entry_price"]):
            excl["bad_row"] += 1
            continue
        al = alerts_by.get((t["ticker"], t["alert_date"]))
        submit = time(9, 31)
        if al and al["detected_at_et"]:
            det = datetime.fromisoformat(al["detected_at_et"]).time()
            submit = max(submit, time(det.hour, det.minute))
        res = walk_campaign(
            ticker=t["ticker"], alert_date=ad, rs=rs, minutes=minutes, daily=daily,
            submit=submit, orb_high=_f(t["orb_high"]), orb_low=_f(t["orb_low"]),
            atr_14=_f(t["atr_14"]), shares=_f(t["entry_shares"]), integer_shares=True)
        live_risk = _f(t["risk_dollars_actual"]) or _f(t["risk_dollars"])
        live_r = (_f(t["total_pnl"]) / live_risk) if live_risk else None
        stop_recon = rs.stop_price(_f(t["orb_high"]), _f(t["orb_low"]))
        live_partial = any(e.get("reason") == "partial_profit" for e in exits_live)
        rep_r = None
        if res["status"] == "settled" and live_risk:
            rep_r = res["realized_pnl_per_unit"] / live_risk
        rows.append({
            "ticker": t["ticker"], "alert_date": t["alert_date"], "era": rs.name,
            "acct": t["account_mode"], "status": res["status"],
            "reason": res["reason"] or "",
            "stop_recon": round(stop_recon, 4), "stop_live": _f(t["hard_stop"]),
            "stop_match": abs(stop_recon - (_f(t["hard_stop"]) or 0)) < 0.011,
            "entered": res["entered"],
            "entry_recon": res["entry_px"], "entry_live": _f(t["entry_price"]),
            "partial_recon": res["partial_fired"], "partial_live": live_partial,
            "final_recon": res["final_reason"] or "",
            "final_live": (exits_live[-1].get("reason") if exits_live else ""),
            "r_recon": None if rep_r is None else round(rep_r, 3),
            "r_live": None if live_r is None else round(live_r, 3),
            "dr": None if (rep_r is None or live_r is None) else round(rep_r - live_r, 3),
            "gap_through": res["gap_through"],
        })
    cols = list(rows[0].keys())
    write_tsv(DATA / "validate_trades.tsv", rows, cols)
    n = len(rows)
    settled = [r for r in rows if r["status"] == "settled"]
    abst = [r for r in rows if r["status"] == "abstain"]
    print(f"validate: {n} first-attempt real trades replayed era-matched "
          f"(excluded: {excl}); settled {len(settled)}, abstained {len(abst)}, "
          f"other {n - len(settled) - len(abst)}")
    print(f"  stop formula match: {sum(r['stop_match'] for r in rows)}/{n}")
    print(f"  entered agreement:  {sum(r['entered'] for r in rows)}/{n} "
          f"(every real trade entered; replay must too)")
    ent = [r for r in rows if r["entered"] and r["entry_live"]]
    diffs = [abs(r["entry_recon"] - r["entry_live"]) / r["entry_live"] * 100 for r in ent]
    if diffs:
        print(f"  entry px |delta|: mean {sum(diffs)/len(diffs):.3f}% "
              f"max {max(diffs):.3f}% (n={len(ent)})")
    pm = [r for r in settled if r["partial_recon"] == r["partial_live"]]
    print(f"  partial-fired agreement: {len(pm)}/{len(settled)}")
    fm = [r for r in settled
          if (r["final_recon"] == "stop_hit") == (r["final_live"] == "stop_hit")]
    print(f"  final-exit-class agreement: {len(fm)}/{len(settled)}")
    dr = [r["dr"] for r in settled if r["dr"] is not None]
    # `within` computed OUTSIDE the guard: it is read again by the validation block below, and
    # binding it only inside `if dr:` is the UnboundLocalError shape that has bitten this repo
    # twice (deploy gate [5d/7] caught the last one 2026-09-01).
    within = sum(1 for x in dr if abs(x) <= 0.25)
    if dr:
        print(f"  realized R: |dR|<=0.25R on {within}/{len(dr)}; "
              f"mean dR {sum(dr)/len(dr):+.3f}R; "
              f"worst {max(dr, key=abs):+.2f}R")
    for r in settled:
        if r["dr"] is not None and abs(r["dr"]) > 0.25:
            print(f"    DISAGREE {r['ticker']} {r['alert_date']} ({r['era']}): "
                  f"recon {r['r_recon']:+.2f}R vs live {r['r_live']:+.2f}R "
                  f"[{r['final_recon']} vs {r['final_live']}]")
    for r in abst:
        print(f"    ABSTAIN {r['ticker']} {r['alert_date']}: {r['reason']}")

    # ── THE HARNESS GATES ITSELF ──────────────────────────────────────────────────────
    # Wired 2026-09-02. validation_verdict() existed since the day this file shipped and its
    # own docstring said "call this from phase_validate" — nothing did. A gate that has never
    # run is not a gate: the numbers above would have kept printing clean while the agreement
    # behind them rotted, which is precisely the failure mode this harness was built to end
    # (#482's founding finding survived for months because nothing re-checked it).
    #
    # ⚠ THE DENOMINATORS ARE THE WHOLE POINT — each must be the SAME population the baseline
    # measured, or the gate compares two different quantities and fails (or passes) for no
    # reason. The first wiring of this block got two of them wrong and the gate said so:
    #   entry_decision: baseline (33, 33) is "where minute data exists". Dividing by all 44
    #     rows reads 75% and looks like catastrophic degradation; the 11 rows abstaining for
    #     `entry_window_gaps` never had an entry decision to agree ABOUT. Rows abstaining for
    #     `day0_fill_bar_straddles_stop` DID enter — they just cannot be settled — so they stay
    #     in this denominator.
    #   abstain_rate: baseline 0.17 belongs to the 270-alert REPLAY population, not to this
    #     44-trade validation cohort (32% here). It is checked in phase_replay, where that
    #     population actually lives — not asserted here against a number from elsewhere.
    entry_undecidable = [r for r in abst if str(r["reason"]).startswith("entry_window_gaps")]
    entry_decidable = n - len(entry_undecidable)
    observed = {
        "stop_formula_rate": (sum(r["stop_match"] for r in rows) / n) if n else None,
        "entry_decision_rate": (sum(r["entered"] for r in rows) / entry_decidable
                                if entry_decidable else None),
        "exit_class_rate": (len(fm) / len(settled)) if settled else None,
        "realized_r_rate": (within / len(dr)) if dr else None,
    }
    verdict = validation_verdict(
        observed, only={k for k, v in VALIDATION_OWNER.items() if v == "validate"})
    print(f"\n  VALIDATION vs {VALIDATION_BASELINE['as_of']} baseline "
          f"({VALIDATION_BASELINE['cohort']}):")
    for k in ("stop_formula_rate", "entry_decision_rate", "exit_class_rate", "realized_r_rate"):
        v = observed[k]
        print(f"    {k:<22} {'not measured' if v is None else format(v, '.0%')} "
              f"(floor {VALIDATION_MIN[k]:.0%})")
    print(f"    {'entry-decidable rows':<22} {entry_decidable}/{n} "
          f"({len(entry_undecidable)} had no minute data in the entry window)")
    if verdict["ok"]:
        print("  ✅ VALIDATION PASS — output from this harness may be quoted.")
        return
    print("\n  ⛔ VALIDATION FAIL — DO NOT QUOTE ANY NUMBER FROM THIS HARNESS:")
    for f in verdict["failures"]:
        print(f"     - {f}")
    raise SystemExit(2)


def _scoring_context():
    """The inputs re-scoring needs, loaded once. Shared by phase_score and phase_replay.

    Was built twice, identically, in the two phases (2026-09-02 cleanup). The pair matters more
    than the line count: an off-by-one in the prior-close or regime lookup — a `<` that should be
    `<=` — would have had to be corrected in both places and re-verified in both, in a harness
    whose entire value is being provably faithful to the live rules.
    """
    s2, s3 = _load_common()
    conf = {r["id"]: r["confidence_multiplier"]
            for r in read_sections(DATA / "_pull5_out.txt")["CONF"]}
    adv = {(r["ticker"], r["score_date"]): _f(r["adv_20"]) for r in s3["ADV"]}
    regime_rows = sorted(s2["REGIME"], key=lambda r: r["regime_date"])
    return s2, s3, conf, adv, regime_rows


def _score_one(a, rs, daily, adv, regime_rows):
    """Re-score ONE alert under `rs`, with the point-in-time prior close and regime.

    STRICTLY-PRIOR on both lookups (`d < ad`, `regime_date < alert_date`) — the lookahead
    contract. One implementation so the two phases cannot drift apart on it.
    """
    ad = date.fromisoformat(a["alert_date"])
    dbars = daily.get(a["ticker"], {})
    prevs = [d for d in sorted(dbars) if d < ad]
    prev_d = prevs[-1] if prevs else None
    reg = next((r for r in reversed(regime_rows)
                if r["regime_date"] < a["alert_date"]), None)
    return ad, rescore_alert(
        a, rs, adv.get((a["ticker"], prev_d.isoformat() if prev_d else "")),
        dbars[prev_d]["c"] if prev_d else None,
        reg["regime"] if reg else None,
        int(reg["ep_threshold"]) if reg and reg.get("ep_threshold") else None)


def phase_score(args) -> None:
    s2, s3, conf, adv, regime_rows = _scoring_context()
    daily = load_daily()
    rows = []
    for a in s2["ALERTS"]:
        a = {**a, "confidence_multiplier": conf.get(a["id"])}
        rs = get_ruleset(args.ruleset) if args.ruleset else ruleset_as_of(
            date.fromisoformat(a["alert_date"]))
        _ad, res = _score_one(a, rs, daily, adv, regime_rows)
        stored = _f(a["ep_score"])
        res.update(ticker=a["ticker"], alert_date=a["alert_date"], ruleset=rs.name,
                   stored=stored,
                   match=(stored is not None
                          and (min(abs(stored - res["score_lo"]),
                                   abs(stored - res["score_hi"])) <= 0.11)))
        rows.append(res)
    cols = ["ticker", "alert_date", "ruleset", "stored", "score_lo", "score_hi",
            "bar", "admit", "adv_known", "match"]
    write_tsv(DATA / "score_agreement.tsv", rows, cols)
    def _bucket(r):
        return "separation(>=08-22)" if r["alert_date"] >= "2026-08-22" else "legacy(<08-22)"
    for b in ("separation(>=08-22)", "legacy(<08-22)"):
        sub = [r for r in rows if _bucket(r) == b]
        if not sub:
            continue
        m = sum(1 for r in sub if r["match"])
        print(f"score [{b}]: reproduced {m}/{len(sub)} stored ep_scores "
              f"(band match, float unknown); adv known {sum(1 for r in sub if r['adv_known'])}")
    mism = [r for r in rows if not r["match"] and r["alert_date"] >= "2026-08-22"]
    for r in mism:
        print(f"    MISMATCH {r['ticker']} {r['alert_date']}: stored {r['stored']} "
              f"vs [{r['score_lo']}, {r['score_hi']}]")


def phase_replay(args) -> None:
    rs = get_ruleset(args.ruleset)   # raises without an explicit rule-set — by design
    s2, s3, conf, adv, regime_rows = _scoring_context()
    minutes, daily = load_minutes(), load_daily()
    rows = []
    for a in s2["ALERTS"]:
        a = {**a, "confidence_multiplier": conf.get(a["id"])}
        # re-score + re-admit under the SAME explicit rule-set
        ad, sc = _score_one(a, rs, daily, adv, regime_rows)
        submit = time(9, 31)
        if a["detected_at_et"]:
            det = datetime.fromisoformat(a["detected_at_et"]).time()
            submit = max(submit, time(det.hour, det.minute))
        res = walk_campaign(ticker=a["ticker"], alert_date=ad, rs=rs,
                            minutes=minutes, daily=daily, submit=submit)
        res["score_tier_stored"] = a["score_tier"]
        res.update(score_lo=sc["score_lo"], score_hi=sc["score_hi"], admit=sc["admit"])
        rows.append(res)
    cols = ["ticker", "alert_date", "ruleset", "score_tier_stored",
            "score_lo", "score_hi", "admit", "status", "reason",
            "entered", "entry_px", "stop", "target", "partial_fired", "final_reason",
            "realized_r", "gap_through", "day0_missing_minutes", "sessions_abstained"]
    out = DATA / (args.out or f"campaigns_{rs.name}.tsv")
    write_tsv(out, rows, cols)
    n = len(rows)
    st = [r for r in rows if r["status"] == "settled"]
    ab = [r for r in rows if r["status"] == "abstain"]
    ne = [r for r in rows if r["status"] == "no_entry"]
    oh = [r for r in rows if r["status"] == "open_at_horizon"]
    print(f"replay[{rs.name}]: {n} alert campaigns -> settled {len(st)}, "
          f"no_entry {len(ne)}, abstain {len(ab)} ({len(ab)/n*100:.0f}%), "
          f"open_at_horizon {len(oh)}, other {n-len(st)-len(ne)-len(ab)-len(oh)}")
    adm = [r for r in rows if r["admit"] == "admit"]
    ab_adm = sum(1 for r in rows if r["admit"].startswith("abstain"))
    print(f"  re-admission under {rs.name}: admit {len(adm)}, "
          f"reject {sum(1 for r in rows if r['admit'] == 'reject')}, "
          f"abstain {ab_adm}")
    import statistics
    for label, pool in (("all alerts", st),
                        ("re-admitted only", [r for r in st if r["admit"] == "admit"])):
        rs_ = [r["realized_r"] for r in pool if r["realized_r"] is not None]
        if rs_:
            print(f"  settled R [{label}]: n={len(rs_)} mean {statistics.mean(rs_):+.2f} "
                  f"median {statistics.median(rs_):+.2f} sum {sum(rs_):+.1f} "
                  f">=4R {sum(1 for x in rs_ if x >= 4)}")
    from collections import Counter
    print(f"  abstain reasons: {dict(Counter(r['reason'].split(':')[0] for r in ab))}")
    print(f"  written: {out}")

    # The abstain ceiling lives HERE, not in phase_validate: VALIDATION_BASELINE's 0.17 was
    # measured on THIS population (the full alert replay), and phase_validate's 44-trade cohort
    # abstains at a legitimately different rate. Checking it there would compare two different
    # things. Past the ceiling the sample has stopped being a sample and nothing below may be
    # quoted, however clean the means look.
    verdict = validation_verdict({"abstain_rate": len(ab) / n if n else None},
                                 only={"max_abstain_rate"})
    if not verdict["ok"]:
        print("\n  ⛔ VALIDATION FAIL — DO NOT QUOTE ANY NUMBER FROM THIS REPLAY:")
        for f in verdict["failures"]:
            print(f"     - {f}")
        raise SystemExit(2)
    print(f"  ✅ abstain {len(ab)/n:.0%} within the "
          f"{VALIDATION_MIN['max_abstain_rate']:.0%} ceiling "
          f"(baseline {VALIDATION_BASELINE['abstain_rate_replay']:.0%}) — replay is quotable.")


# ── VALIDATION BASELINE — the numbers that make this harness quotable ─────────────────
#
# WHY THIS IS A CONSTANT AND NOT A PARAGRAPH (advisor review, 2026-09-01). This module exists to
# be RE-RUN and CITED. Its authority rests entirely on one thing: that it reproduces what really
# happened. When it was built, that was measured — and then lived only in a card's return message
# and a PLAN note. Nothing would fail if the agreement quietly degraded, and this repo's whole
# recent history is findings that were true when written and cited long after they stopped being
# true (the #482 positives that turned out to be daily-bar replays; four adjacent-quantity errors
# in one day). A harness that says "validated" without a checkable bar is the next one.
#
# Measured 2026-09-01 against the 44 replayable real trades, era-matched:
VALIDATION_BASELINE = {
    "as_of": "2026-09-01",
    "cohort": "44 replayable real live trades, era-matched",
    "stop_formula_exact": (44, 44),        # stop price reproduced exactly
    "entry_decision_exact": (33, 33),      # entered / not-entered, where minute data exists
    "exit_class_agree": (29, 30),          # how the trade ended
    "realized_r_within_0p25": (25, 30),
    "current_era_within_0p16": (4, 4),     # era C — the rows that matter for today's questions
    "entry_price_mean_abs_err_pct": 0.24,
    "abstain_rate_replay": 0.17,           # 270-alert current-rules replay
}

# The bar a re-run must clear before ANY number off this harness may be quoted. Set at the
# measured level minus a deliberate margin: tight enough that real degradation trips it, loose
# enough that one new abstaining row does not.
VALIDATION_MIN = {
    "stop_formula_rate": 1.00,             # must stay exact — it is a formula, not an estimate
    "entry_decision_rate": 0.95,
    "exit_class_rate": 0.90,
    "realized_r_rate": 0.75,
    "max_abstain_rate": 0.30,              # 0.17 measured; beyond 0.30 the sample is not a sample
}


#: which phase is responsible for checking each floor. The two phases measure DIFFERENT
#: populations — phase_validate replays 44 real trades, phase_replay replays every alert — so a
#: floor must be checked where its baseline was measured, or the gate compares two unlike things.
#: `test_ep_replay` asserts this mapping covers VALIDATION_MIN exactly, so a new floor cannot be
#: added and left unchecked by both phases.
VALIDATION_OWNER = {
    "stop_formula_rate": "validate",
    "entry_decision_rate": "validate",
    "exit_class_rate": "validate",
    "realized_r_rate": "validate",
    "max_abstain_rate": "replay",
}


def validation_verdict(observed: dict, only: "set[str] | None" = None) -> dict:
    """PASS/FAIL a re-run against VALIDATION_MIN. Returns {'ok': bool, 'failures': [...]}.

    Called from `phase_validate` and `phase_replay`, which REFUSE to quote their output when it
    fails. The point is that degradation is loud: a harness whose agreement has rotted must stop
    being authoritative on its own, not wait for someone to notice a number looks odd.

    `only` restricts the check to the floors this caller is responsible for (VALIDATION_OWNER).
    Without it every floor is required, and a caller that measured a different population would
    be forced to report a number it has no honest value for — which is how a gate starts getting
    fed a lookalike quantity just to make it green.
    """
    failures = []
    for key, floor in VALIDATION_MIN.items():
        if only is not None and key not in only:
            continue
        if key == "max_abstain_rate":
            v = observed.get("abstain_rate")
            if v is not None and v > floor:
                failures.append(f"abstain rate {v:.0%} exceeds the {floor:.0%} ceiling")
            continue
        v = observed.get(key)
        if v is None:
            failures.append(f"{key} not measured — a re-run must report it")
        elif v < floor:
            failures.append(f"{key} {v:.0%} below the {floor:.0%} floor "
                            f"(baseline measured {VALIDATION_BASELINE['as_of']})")
    return {"ok": not failures, "failures": failures}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("phase", choices=["rulesets", "validate", "score", "replay"])
    ap.add_argument("--ruleset", default=None,
                    help="explicit rule-set (required for replay; validate/score "
                         "default to era-matched ruleset_as_of per row)")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    if args.phase == "rulesets":
        for name, rs in RULESETS.items():
            print(f"{name}: {rs}")
        return
    {"validate": phase_validate, "score": phase_score,
     "replay": phase_replay}[args.phase](args)


if __name__ == "__main__":
    main()
