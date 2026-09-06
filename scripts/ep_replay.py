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
  - The Day 3-5 ladder partial is ERA-SWITCHED (RuleSet.ladder_partial, 2026-09-03). Until
    then THE HARNESS TOOK IT AND LIVE DID NOT: live_tracker.py:1076 passes
    `skip_partial_decision=bool(PROFIT_TRIGGER_R)` — set since the +2R partial landed 08-01 —
    so live has skipped the day-3/5 partial decision for every era-B/C trade. `ruleset_as_of`
    now takes it only before 2026-08-01 (era A, where it WAS live). Measured before the switch:
    it moved 14 of 267 campaigns and flipped CORT and ATRO from small wins to small losses;
    a replay that books a partial live stands down is optimistic on every runner rule, which
    is exactly the direction that flatters a harvest finding.
  - Same-day-after-partial: BEFORE 2026-08-08 (RuleSet.breakeven_at_partial False) the
    resting stop stays at the ORIGINAL stop and breakeven enters via the ladder's effective
    stop from the NEXT session (FIGS 08-07 stopped at the original). FROM 08-08 (#548,
    breakeven_at_partial True — era C) `_walk_leg` raises the resting stop to entry AT the
    partial, the same session (ETON 08-14 / CRWD 08-28 stopped at breakeven). This bullet
    said "stays at the original" for every era until 2026-09-03 — stale against the code
    it describes; the code is what `validate` validated.
  - Re-entry is OPT-IN (RuleSet.attempts=2 + reentry_signal; Phase 3, 2026-09-03): one leg
    after a full stop-out via the #5 lineage's three placeable signals, each leg its own 1R.
    `validate` never enables it — the 6 real attempt-2 trades are excluded from agreement and
    counted, so the fill contract is validated on first attempts only.
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
from dataclasses import dataclass, replace
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
# Dated switch table — lives in agents/market_intelligence/rule_eras.py since 2026-09-03
# (#482): the #482 live-fill counterfactual recorder and system_review's era pins read the
# SAME dates, so the harness and the forward recorder cannot disagree about an era boundary
# (P15: a second copy is a fork). Provenance for every line is documented there. The names
# are re-exported here unchanged so every probe that reads `ep.STOP_2R_DATE` still works.
#   10:00 ET unfilled-cancel     era B/C     (CLAUDE.md ORB window; era-A fills as late as
#                                             11:35 prove no cancel then — KURA 04-17)
from agents.market_intelligence.rule_eras import (  # noqa: E402
    BREAKEVEN_AT_PARTIAL_DATE,
    PARTIAL_LIVE_DATE,
    SEP_SCORE_DATE,
    STOP_2R_DATE,
    TRAIL_PRIOR_CLOSES_DATE,
)


@dataclass(frozen=True)
class RuleSet:
    name: str
    score_separation: bool          # True -> SCORE_WEIGHTS + bar 65; False -> legacy + per-regime bar
    stop_mode: str                  # "orb_low" | "entry_minus_2r"
    intraday_partial_r: float | None  # None = no +2R partial (era A); 2.0 since 2026-08-01
    trail_prior_closes: bool        # #548: trail sees the stock's own closes
    entry_cancel: time | None       # unfilled entry cancelled at this ET time (None = end of day)
    breakeven_at_partial: bool = False  # #548: partial moves the resting stop to entry at once
    # 2026-09-06: the ORB SUBMISSION window's close. Default 09:45 = today's live rule
    # (CLAUDE.md: HIGHs at 09:45-09:59 -> WINDOW_OUT_OF_ORB), so every existing rule-set is
    # byte-identical. Exists ONLY so the window can be counterfactualled: it is the largest
    # single skip class we have (11 fires in 30 days, 29 in 90) and the outcome was previously
    # unmeasurable because the harness enforced the same cut-off it was meant to test.
    submit_window_end: time = time(9, 45)
    # ── #545 Phase 3 extensions (2026-09-03). Every field below defaults to the LIVE
    # behaviour so the era rule-sets and `validate` are byte-identical to before. ──
    ladder_partial: bool = True     # the day-3/5 ladder partial: LIVE only while
                                    # PROFIT_TRIGGER_R was unset (< 2026-08-01) — see the
                                    # KNOWN DEVIATIONS entry; era B/C stand it down
    adr_k: float | None = None      # stop_mode "adr_k": stop = orb_high − k × ADR20$ (day-1
                                    # anchor = orb_high, the pre-fill entry proxy live uses)
    target_frame: str = "orb"       # "orb" = +2R pinned to entry−orb_low (live since 08-16,
                                    # profit_target_r_per_share); "own" = +2R of the placed
                                    # stop's distance — the 08-06 moving-target frame
    runner_rule: str = "live"       # what governs the 2/3 after the +2R partial: "live" =
                                    # the ladder (apply_daily_exit_step); else one of
                                    # RUNNER_RULES (the #2 lineage's 13, mirrored exactly)
    attempts: int = 1               # 2 = one re-entry leg after a full stop-out
    reentry_signal: str | None = None  # "sd_5m_clear" | "ndo_o5l" | "ndo_pdl" (the #5 legs)

    def stop_price(self, orb_high: float, orb_low: float,
                   adr_dollar: float | None = None) -> float:
        """The protective stop this rule-set places. Formula provenance:
        orb_low        — the original OTO bracket stop (CLAUDE.md Paper Trading).
        entry_minus_2r — order_manager ~L498: stop = 2*orb_low − orb_high (R = orb range;
                         sizing self-halves through the doubled distance).
        adr_k          — orb_high − k × ADR20$ (Phase 3, never live): the day-2+ band's basis
                         (delayed_entry_shadow.compute_ep_adr_dollar) moved to day 1, with
                         the ADR% × orb_high because the EP-day close is unknowable at 9:31.
                         Missing ADR -> ValueError; the caller abstains, never substitutes.
        Validated per-trade against mi_live_trades.hard_stop by `validate`."""
        if self.stop_mode == "orb_low":
            return orb_low
        if self.stop_mode == "entry_minus_2r":
            return 2 * orb_low - orb_high
        if self.stop_mode == "adr_k":
            if self.adr_k is None or adr_dollar is None or adr_dollar <= 0:
                raise ValueError("adr_k stop needs adr_k and a positive ADR$")
            return orb_high - self.adr_k * adr_dollar
        raise ValueError(f"unknown stop_mode {self.stop_mode!r}")


RULESETS: dict[str, RuleSet] = {
    "era_a": RuleSet("era_a", False, "orb_low", None, False, None, ladder_partial=True),
    "era_b": RuleSet("era_b", False, "orb_low", 2.0, False, time(10, 0), ladder_partial=False),
    "era_c": RuleSet("era_c", True, "entry_minus_2r", 2.0, True, time(10, 0), True,
                     ladder_partial=False),
}
RULESETS["current"] = RULESETS["era_c"]

# ── 2026-09-05, operator-approved A/B: "yes, test it" ──────────────────────────────────
# era_c with the ONE step removed that #545's design doc identifies as the tail-killer: the
# breakeven-at-partial move. Everything else is byte-identical to `current`, so any difference
# in the read is attributable to that step alone. HARNESS-ONLY — this rule-set is never
# returned by `ruleset_as_of()` (which builds era rule-sets by DATE) and nothing live reads it.
RULESETS["era_c_no_breakeven"] = replace(RULESETS["era_c"], name="era_c_no_breakeven",
                                         breakeven_at_partial=False)

# 2026-09-06: era_c with the ORB SUBMISSION window widened 09:45 -> 10:00, and NOTHING else.
# Answers the only question the existing orb_extension shadow cannot: that shadow is fed from
# orders we ALREADY placed, so a name skipped at window:out_of_orb never enters it. HARNESS-ONLY.
RULESETS["era_c_late_window"] = replace(RULESETS["era_c"], name="era_c_late_window",
                                        submit_window_end=time(10, 0))

# 2026-09-06 — THE HARVEST SWEEP (#545 Phase 1). era_c takes a partial at +2R and that is
# the step the 09-05 A/B showed converting a 5R and a 2R into two +0.33R scratches. These
# vary ONLY `intraday_partial_r`: no partial at all, or a LATER one. Nothing else moves,
# so any difference is attributable to the harvest schedule alone. HARNESS-ONLY.
for _pr in (None, 5.0, 8.0, 10.0):
    _nm = "era_c_partial_none" if _pr is None else f"era_c_partial_{int(_pr)}r"
    RULESETS[_nm] = replace(RULESETS["era_c"], name=_nm, intraday_partial_r=_pr)

# The #2 lineage's post-partial rules (scripts/probes/_bt_replay.py RUNNER_RULES), mirrored
# so that harness can retire. "live" is the ladder itself; "live_trail_be" is the same rule
# re-implemented harness-side and is asserted equal to "live" by the Phase 3 sweep.
RUNNER_RULES = ("breakeven", "hard", "live_trail_be", "sma10", "sma20", "atr1", "atr2",
                "gb25", "gb50", "t3", "t5", "t10", "t20")
REENTRY_SIGNALS = ("sd_5m_clear", "ndo_o5l", "ndo_pdl")


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
        ladder_partial=d < PARTIAL_LIVE_DATE,
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


# ── Volatility inputs (from the DAILY capture; strictly-prior sessions, never the day) ──

def adr20_pct(dbars: dict[date, dict], before: date) -> tuple[float | None, int]:
    """Mean (high−low)/close over the <=20 sessions strictly BEFORE `before`, as a FRACTION.
    Same arithmetic as delayed_entry_shadow.compute_adr20 (the day-2+ band's basis) and the
    08-06 stop-floor read's ADR20. (None, n) below 10 usable sessions — abstain, never default."""
    pre = [dbars[d] for d in sorted(dbars) if d < before]
    vals = [(b["h"] - b["l"]) / b["c"] for b in pre[-20:]
            if b.get("h") is not None and b.get("l") is not None and b.get("c")]
    if len(vals) < 10:
        return None, len(vals)
    return sum(vals) / len(vals), len(vals)


def atr14_abs(dbars: dict[date, dict], before: date) -> float | None:
    """Absolute ATR14 through the session before `before` — the #2 lineage's own
    arithmetic (_runner_sweep.atr14_abs), needed by its atr1/atr2 runner rules."""
    rows = [dbars[d] for d in sorted(dbars) if d < before][-35:]
    rows = [r for r in rows if r.get("h") is not None and r.get("l") is not None
            and r.get("c") is not None]
    if len(rows) < 10:
        return None
    trs = [max(r["h"] - r["l"], abs(r["h"] - p["c"]), abs(r["l"] - p["c"]))
           for p, r in zip(rows, rows[1:])]
    w = trs[-14:]
    return sum(w) / len(w) if w else None


def load_minutes_extra() -> dict[tuple[str, date], list[dict]]:
    """SUPPLEMENTARY minute bars for sessions AFTER an alert day (the #562 backfill capture,
    scripts/probes/_562bf_minute.tsv.gz: 245 tickers, 2026-05-08 → 08-31, mi_intraday_bars
    verbatim). Used ONLY by the attempt-2 leg and the stop-minute lookup on later sessions —
    never for day 0, so `validate` and every day-1 number stay byte-identical to the primary
    capture. Missing file -> empty dict (the leg abstains, counted)."""
    import gzip
    path = REPO / "scripts" / "probes" / "_562bf_minute.tsv.gz"
    by: dict[tuple[str, date], list[dict]] = {}
    if not path.exists():
        return by
    with gzip.open(path, "rt") as fh:
        for line in fh:
            p = line.rstrip("\n").split("|")
            if len(p) != 8 or p[0] == "ticker":
                continue
            try:
                dt = datetime.fromtimestamp(int(p[2]) / 1000, tz=_ET)
                bar = {"m": dt, "o": float(p[3]), "h": float(p[4]),
                       "l": float(p[5]), "c": float(p[6])}
            except ValueError:
                continue
            if time(9, 30) <= dt.time() < time(16, 0):
                by.setdefault((p[0], dt.date()), []).append(bar)
    for bars in by.values():
        bars.sort(key=lambda b: b["m"])
    return by


# ── Attempt-2 signals (the #5 lineage's three placeable legs, mirrored) ──────────────

_MIN_R_UNIT_FRAC = 0.003     # #5's degenerate-leg guard: r-unit >= 0.3% of entry


def _w5(m: datetime) -> int:
    """Aligned 5-minute window index from 09:30 (window 0 = 09:30-09:34)."""
    return ((m.hour * 60 + m.minute) - 570) // 5


def signal_sd_5m_clear(day_bars: list[dict], stop_minute: datetime) -> dict | None:
    """Same-day: the first COMPLETE aligned 5-min window strictly after the stop-out bar
    defines a range; re-enter AT its high on a later 1-min bar that clears it; stop = its
    low. (_545_reentry_sweep.sig_5m_clear — `orb_5m_reentry_hybrid_replay`.)"""
    stop_w = _w5(stop_minute)
    rng = None
    for b in day_bars:
        w = _w5(b["m"])
        if w <= stop_w:
            continue
        if rng is None:
            rng = {"w": w, "h": b["h"], "l": b["l"]}
        elif w == rng["w"]:
            rng["h"], rng["l"] = max(rng["h"], b["h"]), min(rng["l"], b["l"])
        elif b["h"] >= rng["h"]:
            return {"entry": rng["h"], "minute": b["m"], "stop": rng["l"],
                    "note": f"range {rng['l']:.2f}-{rng['h']:.2f}"}
    return None


def signal_ndo_o5l(next_bars: list[dict]) -> dict | None:
    """Next session: enter at the open of the first bar at/after 09:35; stop = the low of
    the first five minutes. (_545_reentry_sweep.sig_nextopen_o5l.)"""
    first5 = [b for b in next_bars if b["m"].time() < time(9, 35)]
    after = [b for b in next_bars if b["m"].time() >= time(9, 35)]
    if not first5 or not after:
        return None
    return {"entry": after[0]["o"], "minute": after[0]["m"],
            "stop": min(b["l"] for b in first5), "note": "stop=first-5m low"}


def signal_ndo_pdl(next_bars: list[dict], stop_day_low: float | None) -> dict | None:
    """Next session: enter at the 09:30 open, unconditional; stop = the stop-out day's low.
    (_545_reentry_sweep.sig_nextopen_pdl.)"""
    if not next_bars or stop_day_low is None:
        return None
    return {"entry": next_bars[0]["o"], "minute": next_bars[0]["m"],
            "stop": stop_day_low, "note": "stop=stop-day low"}


# ── One campaign, end to end ─────────────────────────────────────────────────────────

def walk_campaign(*, ticker: str, alert_date: date, rs: RuleSet,
                  minutes: dict, daily: dict[str, dict[date, dict]],
                  submit: time = time(9, 31),
                  orb_high: float | None = None, orb_low: float | None = None,
                  atr_14: float | None = None,
                  shares: float | None = None, integer_shares: bool = False,
                  minutes_extra: dict | None = None) -> dict:
    """Replay one (ticker, alert day) campaign under rule-set `rs`, entry to final exit.
    ORB comes from the stored trade row when given (a stored fact of the day), else from
    the 9:30 minute bar. `shares=None` -> normalized fractional sizing (1 risk unit).
    Returns a dict with status/abstain accounting; never fabricates a fill.

    Phase 3 (2026-09-03): the walk after a fill lives in `_walk_leg` so an attempt-2 leg
    (rs.attempts == 2, rs.reentry_signal) runs through the SAME fill/stop/target/ladder
    mechanics as the first attempt — each attempt is its own 1-risk-unit leg, and the
    campaign's R is the SUM of its legs (the per-name accounting Axis 5 requires)."""
    out = {"ticker": ticker, "alert_date": alert_date, "ruleset": rs.name,
           "status": None, "reason": None, "entered": False, "entry_px": None,
           "stop": None, "target": None, "exits": [], "realized_pnl_per_unit": None,
           "realized_r": None, "partial_fired": False, "final_reason": None,
           "gap_through": False, "day0_missing_minutes": None,
           "sessions_abstained": 0, "flags": [],
           # Phase 3 columns
           "adr_pct": None, "adr_dollar": None, "stop_width_adr": None, "pnl_adr": None,
           "mark_r": None, "attempts_fired": 0, "leg2_status": None, "leg2_reason": None,
           "leg2_r": None, "leg2_pnl_adr": None, "campaign_r": None}
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
    dbars = daily.get(ticker, {})
    adr_pct, adr_n = adr20_pct(dbars, alert_date)
    adr_dollar = adr_pct * orb_high if adr_pct else None
    out.update(adr_pct=adr_pct, adr_dollar=adr_dollar)
    if rs.stop_mode == "adr_k" and adr_dollar is None:
        out.update(status="abstain", reason=f"no_adr20:{adr_n}_sessions")
        return out
    stop = rs.stop_price(orb_high, orb_low, adr_dollar)
    if stop <= 0:
        out.update(status="no_trade", reason="stop_at_or_below_zero")
        return out
    out["stop"] = stop
    if rs.entry_cancel is not None and submit >= rs.submit_window_end:
        # CLAUDE.md ORB window: HIGHs at 9:45-9:59 -> WINDOW_OUT_OF_ORB, no submission.
        # Reads the rule-set (default 09:45 = the live rule) so a variant can widen it.
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
    if entry_px - stop <= 0:
        out.update(status="abstain", reason="nonpositive_risk_per_share")
        return out

    # +2R target. "orb": the LIVE R frame (profit_target_r_per_share: magna53 frames off
    # entry − orb_low, NOT the placed stop; that function owns the rule). "own": +2R of
    # the placed stop's own distance — the 08-06 frame, kept ONLY as the mechanism check.
    target = None
    if rs.intraday_partial_r:
        if rs.target_frame == "orb":
            r_ps = profit_target_r_per_share("magna53", entry_px, stop, orb_low)
        elif rs.target_frame == "own":
            r_ps = entry_px - stop
        else:
            raise ValueError(f"unknown target_frame {rs.target_frame!r}")
        if r_ps is not None:
            target = entry_px + rs.intraday_partial_r * r_ps
    out["target"] = target
    if adr_dollar:
        out["stop_width_adr"] = (entry_px - stop) / adr_dollar

    fill_idx = next(i for i, b in enumerate(bars0) if b["m"] == fill["minute"])
    leg = _walk_leg(ticker=ticker, leg_date=alert_date, entry_px=entry_px, stop=stop,
                    target=target, bars=bars0, fill_idx=fill_idx, rs=rs, daily=daily,
                    shares=shares, integer_shares=integer_shares, adr_dollar=adr_dollar,
                    minutes_extra=minutes_extra or {})
    for k in ("status", "reason", "exits", "final_reason", "partial_fired", "gap_through",
              "sessions_abstained", "realized_pnl_per_unit", "realized_r", "pnl_adr",
              "mark_r"):
        out[k] = leg[k]
    out["attempts_fired"] = 1
    if leg["status"] == "abstain":
        return out

    # ── Attempt 2: one re-entry leg after a FULL stop-out (no partial banked) ──
    if (rs.attempts >= 2 and leg["status"] == "settled"
            and leg["final_reason"] == "stop_hit" and not leg["partial_fired"]):
        if rs.reentry_signal not in REENTRY_SIGNALS:
            raise ValueError(f"attempts=2 needs reentry_signal in {REENTRY_SIGNALS}")
        leg2 = _attempt_two(ticker=ticker, alert_date=alert_date, stop_day=leg["stop_day"],
                            stop_minute=leg["stop_minute"], stop_px=leg["stop_px"],
                            rs=rs, minutes=minutes, daily=daily,
                            minutes_extra=minutes_extra or {}, shares=shares,
                            integer_shares=integer_shares, adr_dollar=adr_dollar)
        out.update(leg2_status=leg2["status"], leg2_reason=leg2.get("reason"))
        if leg2["status"] in ("settled", "open_at_horizon"):
            out["attempts_fired"] = 2
            out["leg2_r"] = leg2["realized_r"]
            out["leg2_pnl_adr"] = leg2["pnl_adr"]
            out["flags"].append(f"leg2:{leg2.get('note', '')}")
            if leg2["status"] == "open_at_horizon":
                out["status"] = "open_at_horizon"
                out["mark_r"] = (out["realized_r"] or 0.0) + (leg2["mark_r"] or 0.0)
    if out["status"] == "settled":
        out["campaign_r"] = (out["realized_r"] or 0.0) + (out["leg2_r"] or 0.0)
    return out


def _attempt_two(*, ticker, alert_date, stop_day, stop_minute, stop_px, rs, minutes, daily,
                 minutes_extra, shares, integer_shares, adr_dollar) -> dict:
    """Compute the re-entry signal after a stop-out and walk it as a fresh 1-risk-unit leg.
    Same-day bars come from the primary capture on day 0 or the supplementary capture on a
    later session; next-session bars only from the supplementary capture. No bars -> the
    leg ABSTAINS (counted) — never a daily-grain fill."""
    def bars_for(d: date) -> list[dict]:
        if d == alert_date:
            return minutes.get((ticker, d), [])
        return minutes_extra.get((ticker, d), [])

    day_bars = bars_for(stop_day)
    if stop_minute is None:
        # forward-daily stop-out: locate the first bar at/under the resting stop
        hit = next((b for b in day_bars if b["l"] <= stop_px), None)
        if hit is None:
            return {"status": "abstain", "reason": "leg2_no_stop_minute"}
        stop_minute = hit["m"]
    if rs.reentry_signal == "sd_5m_clear":
        if not day_bars:
            return {"status": "abstain", "reason": "leg2_no_same_day_bars"}
        sig = signal_sd_5m_clear(day_bars, stop_minute)
        leg_date = stop_day
    else:
        nxt = stop_day
        next_bars: list[dict] = []
        for _ in range(6):
            nxt += timedelta(days=1)
            if nxt.weekday() >= 5:
                continue
            next_bars = bars_for(nxt)
            if next_bars:
                break
        if not next_bars:
            return {"status": "abstain", "reason": "leg2_no_next_session_bars"}
        if nxt > LAST_SETTLED:
            return {"status": "abstain", "reason": "leg2_next_session_past_horizon"}
        if rs.reentry_signal == "ndo_o5l":
            sig = signal_ndo_o5l(next_bars)
        else:
            db = daily.get(ticker, {}).get(stop_day)
            sd_low = db["l"] if db and db.get("l") is not None else (
                min(b["l"] for b in day_bars) if day_bars else None)
            sig = signal_ndo_pdl(next_bars, sd_low)
        leg_date = nxt
    if sig is None:
        return {"status": "no_signal", "reason": "leg2_no_signal"}
    entry, stop = sig["entry"], sig["stop"]
    if entry <= stop or (entry - stop) / entry < _MIN_R_UNIT_FRAC:
        return {"status": "no_signal", "reason": "leg2_degenerate_r_unit"}
    target = entry + rs.intraday_partial_r * (entry - stop) if rs.intraday_partial_r else None
    lbars = bars_for(leg_date)
    fill_idx = next(i for i, b in enumerate(lbars) if b["m"] == sig["minute"])
    leg = _walk_leg(ticker=ticker, leg_date=leg_date, entry_px=entry, stop=stop,
                    target=target, bars=lbars, fill_idx=fill_idx, rs=rs, daily=daily,
                    shares=shares, integer_shares=integer_shares, adr_dollar=adr_dollar,
                    minutes_extra=minutes_extra, fill_at_open=(rs.reentry_signal != "sd_5m_clear"))
    leg["note"] = f"{rs.reentry_signal}@{leg_date} {entry:.2f}/{stop:.2f} {sig['note']}"
    return leg


def _walk_leg(*, ticker, leg_date, entry_px, stop, target, bars, fill_idx, rs, daily,
              shares, integer_shares, adr_dollar, minutes_extra, fill_at_open=False) -> dict:
    """Walk one filled leg from its fill bar to settlement: the day-of minute walk, then the
    forward daily walk under the LIVE ladder (runner_rule "live") or one of the #2 lineage's
    post-partial rules. Returns status / exits / R and the stop-out anchor (day, minute, px)
    an attempt-2 leg needs. Sizing: `shares=None` -> 1 risk unit on THIS leg's own stop."""
    out = {"status": None, "reason": None, "exits": [], "final_reason": None,
           "partial_fired": False, "gap_through": False, "sessions_abstained": 0,
           "realized_pnl_per_unit": None, "realized_r": None, "pnl_adr": None,
           "mark_r": None, "stop_day": None, "stop_minute": None, "stop_px": None}
    if shares is None:
        shares = 1.0 / (entry_px - stop)      # 1 risk-dollar unit
    risk_denom = shares * (entry_px - stop)
    remaining = float(shares)
    partial_taken = False
    exits: list[dict] = []
    runner = rs.runner_rule
    if runner != "live" and runner not in RUNNER_RULES:
        raise ValueError(f"unknown runner_rule {runner!r}; known: live, {RUNNER_RULES}")
    # #2's floor rule: breakeven only for the breakeven-family rules; the hard stop stays
    # for every other runner (the "hard-stop-stays" cost side is part of each rule).
    be_floor = runner in ("live", "breakeven", "live_trail_be")

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

    def stopped(px: float, when, d: date, minute) -> None:
        nonlocal remaining
        book(px, remaining, "stop_hit", when)
        remaining = 0.0
        out["final_reason"] = "stop_hit"
        out.update(stop_day=d, stop_minute=minute, stop_px=px)

    # ── Day-of minute walk from the fill bar ──
    cur_stop = stop
    closed = False
    fb = bars[fill_idx]
    if fb["l"] <= stop:
        if target is not None and fb["h"] >= target:
            # stop AND target both inside the fill bar — order unknowable at 1-min grain
            out.update(status="abstain", reason="day0_fill_bar_stop_and_target")
            return out
        # Provable ordering: entry fills at the first touch >= orb_high (or at the open
        # for an open-priced leg); close < stop means the path DESCENDED through the stop
        # after its high-water moment, so the stop fill is post-entry. Close >= stop leaves
        # the order unknowable -> abstain.
        if fb["c"] < stop:
            stopped(stop, fb["m"], leg_date, fb["m"])
            closed = True
        else:
            out.update(status="abstain", reason="day0_fill_bar_straddles_stop")
            return out
    if (not closed and target is not None and fb["h"] >= target and fb["c"] >= stop
            and not fill_at_open):
        # Same provability does not exist for target-vs-nothing: a target touch in the
        # fill bar after the cross is orderable (target > orb_high >= any pre-fill price
        # only when orb crossed first) — the touch >= target necessarily post-dates the
        # first >= orb_high touch when target > orb_high, which +2R guarantees. An
        # open-priced leg has no such ordering -> the touch is left to the next bar.
        if take_partial(target, fb["m"]) and rs.breakeven_at_partial and be_floor:
            cur_stop = max(cur_stop, entry_px)
    for b in bars[fill_idx + 1:]:
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
            stopped(px, b["m"], leg_date, b["m"])
            closed = True
        elif hit_tgt:
            if take_partial(target, b["m"]) and rs.breakeven_at_partial and be_floor:
                cur_stop = max(cur_stop, entry_px)

    # ── Forward daily walk: the LIVE ladder + the resting-stop overlay, or a runner rule ──
    last_close = bars[-1]["c"] if bars else entry_px
    if not closed:
        dbars = daily.get(ticker, {})
        prior = [dbars[d]["c"] for d in sorted(dbars)
                 if d < leg_date and dbars[d]["c"] is not None]
        d0 = dbars.get(leg_date)
        held = [d0["c"]] if d0 and d0.get("c") is not None else [last_close]
        atr14 = atr14_abs(dbars, leg_date)
        state = seed_exit_state(
            alert_date=leg_date, entry_price=entry_px, hard_stop=stop,
            remaining_shares=remaining, partial_taken=partial_taken,
            breakeven_active=partial_taken and be_floor, exits=list(exits))
        resting = cur_stop    # the broker's resting stop; raise-only, per live EOD updates
        post_sessions = 0
        d = leg_date
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
            last_close = b["c"]
            hit_tgt = (target is not None and not state["partial_taken"]
                       and b["h"] >= target)
            if hit_tgt and b["l"] <= resting:
                out.update(status="abstain", reason=f"fwd_stop_and_target_same_day:{d}")
                return out
            if hit_tgt:
                remaining = state["remaining_shares"]
                partial_taken = state["partial_taken"]
                if take_partial(target, d) and rs.breakeven_at_partial and be_floor:
                    resting = max(resting, entry_px)
                state["remaining_shares"] = remaining
                state["partial_taken"] = True
                state["breakeven_active"] = be_floor
                state["exits"] = list(exits)
                post_sessions = 0
            if runner != "live" and state["partial_taken"]:
                # ── the #2 lineage's post-partial walk, mirrored (_bt_replay.replay_trade) ──
                if hit_tgt:
                    held.append(b["c"])       # the partial bar is session 0, never a check
                    continue
                post_sessions += 1
                lvl = entry_px if be_floor else stop
                if runner in ("atr1", "atr2") and atr14 and held:
                    lvl = max(lvl, max(held) - (1.0 if runner == "atr1" else 2.0) * atr14)
                if b["l"] <= lvl:
                    px = b["o"] if (b["o"] is not None and b["o"] < lvl) else lvl
                    if px != lvl:
                        out["gap_through"] = True
                    stopped(px, d, d, None)
                    out["final_reason"] = "stop_hit"
                    closed = True
                    break
                held.append(b["c"])
                c = b["c"]
                exit_now = None
                if runner in ("sma10", "sma20", "live_trail_be"):
                    tc = prior + held
                    s10 = sum(tc[-10:]) / 10 if len(tc) >= 10 else None
                    s20 = sum(tc[-20:]) / 20 if len(tc) >= 20 else None
                    if runner == "sma10":
                        s = s10
                    elif runner == "sma20":
                        s = s20
                    else:
                        s = (s10 if (s10 is not None and s10 > s20) else s20) \
                            if s20 is not None else s10
                    if s is not None and c < s:
                        exit_now = "sma_trail_stop"
                elif runner in ("gb25", "gb50"):
                    keep = 0.75 if runner == "gb25" else 0.50
                    peak = max(held)
                    if peak > entry_px and c < entry_px + keep * (peak - entry_px):
                        exit_now = "giveback_close"
                elif runner in ("t3", "t5", "t10", "t20"):
                    if post_sessions >= int(runner[1:]):
                        exit_now = "time_close"
                if exit_now:
                    book(c, remaining, exit_now, d)
                    remaining = 0.0
                    out["final_reason"] = exit_now
                    closed = True
                    break
                continue
            state["hard_stop"] = resting
            step = apply_daily_exit_step(
                state, {"l": b["l"], "c": b["c"]}, d,
                integer_partial_shares=integer_shares,
                skip_partial_decision=not rs.ladder_partial,
                prior_closes=(prior if rs.trail_prior_closes else None))
            state.update(remaining_shares=step.new_remaining,
                         partial_taken=step.new_partial_taken,
                         breakeven_active=step.new_breakeven_active,
                         exits=step.new_exits,
                         running_closes=step.new_running_closes)
            held.append(b["c"])
            if step.closed:
                px, reason = step.close_price, step.close_reason
                if reason == "stop_hit" and b["o"] is not None and b["o"] < px:
                    px = b["o"]           # gap-through honesty: the resting stop fills at the open
                    out["gap_through"] = True
                exits = [e for e in step.new_exits]
                exits[-1] = {**exits[-1], "price": px,
                             "pnl": (px - entry_px) * exits[-1]["shares"]}
                out["final_reason"] = reason
                if reason == "stop_hit":
                    out.update(stop_day=d, stop_minute=None, stop_px=px)
                remaining = 0.0
                closed = True
            else:
                exits = list(step.new_exits)
                remaining = step.new_remaining
                resting = max(resting, step.effective_stop)
        out["partial_fired"] = any(e["reason"] == "partial_profit" for e in exits)

    out["exits"] = exits
    if closed:
        out["status"] = "settled"
    pnl = sum(e["pnl"] for e in exits)
    out["realized_pnl_per_unit"] = pnl
    if risk_denom > 0:
        if closed:
            out["realized_r"] = pnl / risk_denom
            if adr_dollar:
                out["pnl_adr"] = (pnl / shares) / adr_dollar
        elif out["status"] == "open_at_horizon":
            # a MARK, never a return: the open remainder at the last settled close
            out["mark_r"] = (pnl + (last_close - entry_px) * remaining) / risk_denom
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

    # ── 2026-09-05, operator: "how can we make sure this study works going forward without
    # all the caveats you listed, that is the more important point." Four traps bit a single
    # evening's work and every one of them was caught by a human reading the output rather
    # than by the harness. They are structural, they recur, and they are all decidable HERE:
    #
    #   1. CENSORING. A settled-only summary silently drops open_at_horizon rows — and a
    #      looser exit rule's whole benefit is that it KEEPS POSITIONS OPEN. The 09-05
    #      breakeven A/B lost CRWD exactly this way, and #327's lane reads -0.75R for the
    #      same reason (a stop settles instantly; a winner stays open). Now printed on
    #      every line, so a censored read cannot look complete.
    #   2. NEAR-ZERO STOPS. A two-cent stop makes R meaningless: two such rows once carried
    #      more R than a 1,577-row population. Every study was expected to remember to
    #      exclude them. Now excluded by DEFAULT and the exclusion is stated.
    #   3. THE WRONG STATISTIC. Operator, same day: "big tail is the key ingredient, median
    #      can be somewhat managed with entry and exit." Ranking by median produced three
    #      conclusions that all dissolved on the tail cut. Tail counts now print FIRST.
    #   4. UNSOURCED COVERAGE. "n=66" says nothing about what it is 66 OF. The walkable
    #      denominator now prints beside it.
    _NEAR_ZERO_STOP_PCT = 0.5   # |entry-stop|/entry, in percent — the #621/#623 class

    def _stop_width_pct(r):
        try:
            e, sp = float(r["entry_px"]), float(r["stop"])
            return abs(e - sp) / e * 100 if e else None
        except (TypeError, ValueError):
            return None

    _degenerate = [r for r in st
                   if (w := _stop_width_pct(r)) is not None and w < _NEAR_ZERO_STOP_PCT]
    if _degenerate:
        print(f"  ⚠ excluded {len(_degenerate)} settled row(s) with a stop narrower than "
              f"{_NEAR_ZERO_STOP_PCT}% of entry — R is not meaningful there "
              f"({', '.join(sorted(r['ticker'] for r in _degenerate)[:6])})")
    _deg = {id(r) for r in _degenerate}

    for label, pool, openpool in (
            ("all alerts", st, oh),
            ("re-admitted only", [r for r in st if r["admit"] == "admit"],
             [r for r in oh if r["admit"] == "admit"])):
        rs_ = [r["realized_r"] for r in pool
               if r["realized_r"] is not None and id(r) not in _deg]
        if not rs_:
            continue
        p90 = statistics.quantiles(rs_, n=10)[-1] if len(rs_) >= 10 else float("nan")
        # TAIL FIRST — the statistic the operator ruled on 2026-09-05.
        print(f"  R [{label}]: n={len(rs_)}  >=3R {sum(1 for x in rs_ if x >= 3)}"
              f"  >=5R {sum(1 for x in rs_ if x >= 5)}  p90 {p90:+.2f}"
              f"   | median {statistics.median(rs_):+.2f} mean {statistics.mean(rs_):+.2f} "
              f"sum {sum(rs_):+.1f}")
        # CENSORING — stated on the same line it would otherwise distort.
        print(f"     ⚠ {len(openpool)} row(s) STILL OPEN at the horizon and NOT in the above."
              f" A looser exit rule's benefit hides here — never compare rule-sets on settled"
              f" rows alone.")
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
