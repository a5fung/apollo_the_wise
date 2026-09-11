"""Market Strength Map — slice 2: the COMPLEX table (#494). READ-ONLY, no money.

Operator's north star (2026-07-20): *"Do we have a holistic view of where strength is? It can be
crypto, healthcare, gold/silver, whatever it is."*

He ruled the design fork on 2026-08-08: **GROUP them.** A **complex** is an asset anchor plus the
equities that express it, shown together — because a precious-metals move appears in BOTH gold and
the miners, and the relationship between them is itself the signal. The two rejected options
(separate layers / one combined ranking) and why they lost are in
`docs/design/market_strength_map.md`.

**A complex carries TWO readings, and conflating them loses the second** (operator, same day):

1. **DIRECTION** — anchor vs its equity expression. *Are the miners outrunning the metal?*
2. **RISK APPETITE** — senior vs junior INSIDE the complex. *Are the juniors outrunning the
   seniors?* His words: *"if smaller caps rise faster which is expected in a bull market with more
   risk taking, ppl going further into riskier spectrum, this is info. In crypto world, this is
   called alt season."* Naming it that way makes it ONE concept across every asset class rather
   than a crypto curiosity.

⚠ **The risk read is only shown where the pair is REAL.** GDX/GDXJ is senior-vs-junior miners and
XLE/XOP is majors-vs-E&P — both are genuine size/beta splits. Uranium, agriculture and the macro
row have no honest pair in what we hold, so they show DIRECTION only. Two ETFs that differ by
*metal* rather than by *size* (XME vs COPX) would be a fabricated spectrum, and a fabricated
signal is worse than a missing one.

⚠ **This is a READ, not a rule.** It says where strength and risk appetite are; it sizes nothing,
enters nothing, exits nothing.

**Deliberately ships BEFORE any cross-asset ranking.** Ranking gold against a junior miner on one
scale needs a common frame (raw return vs vol-adjusted) that changes what ranks top — a criteria
decision still owed by the operator. The SPREAD needs no such frame to be correct, which is why
it is sequenced first.
"""
from __future__ import annotations

import json
import logging
from datetime import date
from typing import Any

from agents.market_intelligence.db import get_pool, log_audit_event

logger = logging.getLogger(__name__)

# Trading-day lookbacks. Calendar months would drift against holidays; these are bar counts.
_WINDOWS = (("1M", 21), ("3M", 63), ("6M", 126))

# ── The dominance band RE-CALIBRATES ITSELF on every run ──────────────────────────────────
#
# Operator, 2026-08-08: *"this need to be recalibrated, it may become more volatile phase, but
# when and how often"*. The answer is EVERY RUN, from the data — because in this repo a
# threshold a human has to remember to re-measure is a threshold that goes stale, and a stale
# threshold is the exact failure class that keeps recurring here.
#
# The band is the MEDIAN ABSOLUTE 30-day change over the trailing window: a move must beat the
# typical move before it earns the word "leading". Measured 2026-08-08 on the first 97 days it
# came out at 0.71pts — which is why my hand-picked 0.5 was wrong: it labelled the median move
# a direction, i.e. sold noise as signal roughly half the time.
#
# ⭐ AND THE BAND MOVING IS ITSELF THE SIGNAL HE IS ASKING ABOUT. If the typical 30-day move
# widens from 0.7 to 2.0, crypto has entered a more volatile phase — that belongs on the
# surface, not buried inside a constant. `_dominance_band` returns the recent band, the
# baseline band, and whether it has widened materially.
_DOM_BAND_FLOOR = 0.3        # never call a sub-0.3pt move a direction, however quiet the tape
_DOM_BAND_DEFAULT = 0.7      # used ONLY when there is too little history to measure
_DOM_RECENT_DAYS = 60        # "now"
_DOM_BASELINE_DAYS = 240     # "normally"
_DOM_WIDEN_RATIO = 1.5       # recent/baseline above this = a genuinely more volatile phase


def _median(xs: list[float]) -> float | None:
    if not xs:
        return None
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0


def _abs_30d_moves(rows: list[tuple]) -> list[float]:
    """|change| over ~30 days for every day we can pair, oldest-first rows of (date, pct)."""
    out = []
    for i, (d, v) in enumerate(rows):
        prior = next((p for pd, p in rows[:i][::-1] if (d - pd).days >= 30), None)
        if prior is not None:
            out.append(abs(float(v) - float(prior)))
    return out


def _dominance_band(rows: list[tuple]) -> dict:
    """Self-calibrating band + the volatility-phase read. `rows` oldest-first (date, pct)."""
    if not rows:
        return {"band": _DOM_BAND_DEFAULT, "measured": False}
    newest = rows[-1][0]
    recent = _median(_abs_30d_moves([r for r in rows
                                     if (newest - r[0]).days <= _DOM_RECENT_DAYS]))
    baseline = _median(_abs_30d_moves([r for r in rows
                                       if (newest - r[0]).days <= _DOM_BASELINE_DAYS]))
    band = max(recent if recent is not None else _DOM_BAND_DEFAULT, _DOM_BAND_FLOOR)
    widened = bool(recent and baseline and baseline > 0
                   and recent / baseline >= _DOM_WIDEN_RATIO)
    return {"band": round(band, 2), "measured": recent is not None,
            "recent": None if recent is None else round(recent, 2),
            "baseline": None if baseline is None else round(baseline, 2),
            "widened": widened}

# `anchor` = the asset itself. `senior`/`junior` = its equity expression, split by SIZE where that
# split is real. A complex with no honest size pair simply has no `junior`.
COMPLEXES: tuple[dict[str, Any], ...] = (
    {"name": "Precious metals", "anchor": ["GLD", "SLV"], "senior": ["GDX"], "junior": ["GDXJ"]},
    {"name": "Energy", "anchor": ["USO", "UNG"], "senior": ["XLE"], "junior": ["XOP"]},
    # No size pair: URA is the only uranium vehicle we carry; WEAT/CORN are different crops, not
    # different sizes. Direction only — see the module docstring on fabricated spectrums.
    {"name": "Uranium", "anchor": [], "senior": ["URA"], "junior": []},
    {"name": "Agriculture", "anchor": ["WEAT", "CORN"], "senior": [], "junior": []},
    {"name": "Macro backdrop", "anchor": ["TLT", "UUP"], "senior": [], "junior": []},
)

_CLOSES_SQL = """
    SELECT ticker, trade_date, close
      FROM mi_daily_closes
     WHERE ticker = ANY($1::text[]) AND trade_date <= $2
     ORDER BY ticker, trade_date
"""


def _ret(closes: list[float], bars: int) -> float | None:
    """Trailing % return over `bars` trading days. None when the history is short — ABSENT, never
    fabricated from whatever happens to be there."""
    if len(closes) <= bars or closes[-bars - 1] == 0:
        return None
    return (closes[-1] / closes[-bars - 1] - 1.0) * 100.0


def _basket(series: dict[str, list[float]], tickers: list[str], bars: int) -> float | None:
    """Equal-weighted mean return across a basket. A ticker with insufficient history drops out
    rather than dragging the basket to None — but an EMPTY basket stays None."""
    vals = [r for t in tickers if (r := _ret(series.get(t, []), bars)) is not None]
    return sum(vals) / len(vals) if vals else None


async def compute_strength_map(today: date) -> dict:
    """Per complex, per window: anchor return, expression return, DIRECTION spread, and the
    RISK spread (junior − senior) where a real size pair exists. Pure read."""
    tickers = sorted({t for c in COMPLEXES for k in ("anchor", "senior", "junior") for t in c[k]})
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(_CLOSES_SQL, tickers, today)
        # ⚠ `crypto_btc_dominance.slope_30d` LOOKS like the alt-season read and is a DEAD
        # COLUMN: 97 rows since 2026-04-27, every one NULL. The insert in `crypto/ingest.py`
        # writes only (date, dominance_pct, total_mcap_usd) — nothing has ever populated the
        # slope. Operator caught it on the first render ("we've been shadowing for longer").
        #
        # So derive the trend HERE from the dominance series we already store, rather than
        # adding a writer for a field with one consumer. Reported as the CHANGE IN PERCENTAGE
        # POINTS over ~30 days, not a regression slope: "dominance fell 1.4pts in a month" is
        # a sentence he can act on; a slope coefficient is not.
        # 400 rows, not 45: the band is re-derived from the trailing window every run, so it
        # needs the baseline history too — see `_dominance_band`.
        dom_rows = await conn.fetch(
            "SELECT date, dominance_pct FROM crypto_btc_dominance "
            "WHERE date <= $1 ORDER BY date DESC LIMIT 400", today)
        dom = None
        if dom_rows:
            latest = dom_rows[0]
            # Walk back to the first row at least 30 days older; None if history is short —
            # ABSENT, never a fabricated zero.
            prior = next((r for r in dom_rows
                          if (latest["date"] - r["date"]).days >= 30), None)
            asc = [(r["date"], r["dominance_pct"]) for r in reversed(dom_rows)
                   if r["dominance_pct"] is not None]
            dom = {
                "date": latest["date"],
                "dominance_pct": latest["dominance_pct"],
                "change_30d": (float(latest["dominance_pct"]) - float(prior["dominance_pct"]))
                              if prior and prior["dominance_pct"] is not None else None,
                "history_days": (latest["date"] - dom_rows[-1]["date"]).days,
                **_dominance_band(asc),
            }

    series: dict[str, list[float]] = {}
    for r in rows:
        series.setdefault(r["ticker"], []).append(float(r["close"]))

    out = []
    for c in COMPLEXES:
        wins = {}
        for label, bars in _WINDOWS:
            anchor = _basket(series, c["anchor"], bars)
            senior = _basket(series, c["senior"], bars)
            junior = _basket(series, c["junior"], bars)
            expression = _basket(series, c["senior"] + c["junior"], bars)
            wins[label] = {
                "anchor": anchor,
                "expression": expression,
                # DIRECTION: are the equities outrunning the asset?
                "spread": (expression - anchor)
                          if (anchor is not None and expression is not None) else None,
                # RISK APPETITE: juniors over seniors. Only when BOTH sides are real.
                "risk": (junior - senior)
                        if (senior is not None and junior is not None) else None,
            }
        if any(v["anchor"] is not None or v["expression"] is not None for v in wins.values()):
            out.append({"name": c["name"], "windows": wins,
                        "has_risk_pair": bool(c["senior"] and c["junior"])})

    return {"today": today, "complexes": out,
            "btc_dominance": dict(dom) if dom else None}


def _pct(v: float | None) -> str:
    """Fixed width so the columns line up in a Telegram monospace block. `—` means NOT COMPUTED
    (insufficient history or no such leg) — never 0, which would read as "flat"."""
    return f"{'—':>6}" if v is None else f"{v:+6.1f}"


def format_strength_map(data: dict) -> str:
    """Telegram block. Empty string when there is nothing to say — keeps the brief tight."""
    rows = data.get("complexes") or []
    if not rows:
        return ""
    out = ["*🗺 Strength map — the asset vs the stocks that express it*", "```"]
    # Header and data share ONE spacing recipe: 6-wide cells, a space inside each pair, two
    # spaces between the 1M and 3M groups. Written once as a helper so they cannot drift —
    # the first version had a 2-char mismatch and the columns collided on real numbers.
    def _row(label: str, a, b, c_, d) -> str:
        return f"{label[:15]:<15}{a:>6} {b:>6}  {c_:>6} {d:>6}"

    out.append(_row("", "-- 1M", "--", "-- 3M", "--"))
    out.append(_row("", "asset", "stks", "asset", "stks"))
    for c in rows:
        w1, w3 = c["windows"]["1M"], c["windows"]["3M"]
        out.append(_row(c["name"], _pct(w1["anchor"]).strip(), _pct(w1["expression"]).strip(),
                        _pct(w3["anchor"]).strip(), _pct(w3["expression"]).strip()))
        # THE SPREAD is the new information — stated in words, not left to be eyeballed.
        s = w1["spread"]
        if s is not None:
            who = "stocks lead" if s > 0 else "asset leads"
            out.append(f"{'':<15}  {who} by {abs(s):.1f}pts")
        # RISK APPETITE. Shown WHENEVER the size pair is real, including when it is flat —
        # otherwise a quiet reading is indistinguishable from a missing one, and "risk appetite
        # is not moving" is itself information (operator 2026-08-08).
        if c.get("has_risk_pair"):
            r = w1["risk"]
            if r is None:
                out.append(f"{'':<15}  risk: not computed")
            elif abs(r) < 1.0:
                out.append(f"{'':<15}  risk: flat ({r:+.1f}pts jr-vs-sr)")
            else:
                who = "juniors" if r > 0 else "seniors"
                out.append(f"{'':<15}  risk: {who} +{abs(r):.1f}pts "
                           f"— {'risk-ON' if r > 0 else 'risk-off'}")
    dom = data.get("btc_dominance")
    if dom and dom.get("dominance_pct") is not None:
        chg = dom.get("change_30d")
        band = dom.get("band", _DOM_BAND_DEFAULT)
        if chg is None:
            tag = f" (only {dom.get('history_days', 0)}d of history — need 30)"
        elif chg <= -band:
            tag = f" {chg:+.1f}pts/30d — alts leading (ALT SEASON tilt)"
        elif chg >= band:
            tag = f" {chg:+.1f}pts/30d — BTC leading"
        else:
            tag = f" {chg:+.1f}pts/30d — TYPICAL, no tilt"
        out.append(f"{'Crypto':<15}BTC dominance {float(dom['dominance_pct']):.1f}%{tag}")
        # The number is meaningless without its scale, and the scale is re-derived every run —
        # so print the band actually in use rather than a remembered constant.
        src = "measured" if dom.get("measured") else "default, too little history"
        out.append(f"{'':<15}  (share of ALL crypto, out of 100 · typical 30d move "
                   f"{band}pts — {src})")
        # ⭐ A WIDENING BAND IS ITSELF THE SIGNAL (operator 2026-08-08). If moves are getting
        # bigger, crypto has entered a more volatile phase — that belongs on the surface, not
        # buried inside a threshold that quietly re-tunes.
        if dom.get("widened"):
            out.append(f"{'':<15}  ⚠ MORE VOLATILE PHASE: recent moves {dom['recent']}pts vs "
                       f"{dom['baseline']}pts normally")
    out.append("```")
    out.append("_spread = stocks minus asset · risk = juniors minus seniors "
               "(crypto calls it alt season) · a READ, not a rule_")
    return "\n".join(out)


async def build_strength_map_section(today: date) -> str:
    """Assemble + render. Raises to the caller on DB failure; the brief fail-opens loudly so a
    map problem can never cost the operator the rest of his briefing."""
    return format_strength_map(await compute_strength_map(today))


# ── #579 — the AD-HOC spread-crossing alert ────────────────────────────────────────────────
#
# Operator's proving case: this module already computes "are the miners outrunning the metal?"
# — and it only ever surfaced inside the WEEKLY briefing, so he found the 15.3pt precious-metals
# lead on Twitter before Apollo told him. *"what I really love is not preset reviews and
# notification, but ad hoc things that Apollo can discover and send me whenever it deems it's
# relevant and the timing is right."* The computation was never the gap. The cadence was.
#
# THE PRIMITIVE IS `_dominance_band`, GENERALISED — SAME SHAPE, DIFFERENT STATISTIC. That
# function is a self-calibrating band for a CLASSIFIER (median, so it can be told apart from
# "typical" about half the time — fine inside a 3-way weekly read). An ad-hoc trigger needs a
# rare-tail bar, not a typical-move one: `docs/analysis/579_spread_firing_distribution_2026-09-11.md`
# measured the median-band ported unchanged fires 50.7%/47.9% of ALL days — worthless as a
# trigger. **Each series' own 75TH PERCENTILE of |30-session change|, recomputed from trailing
# history every run**, prices out at ~1.2 crossings/month per complex. That number is MEASURED,
# not guessed — the two percentile constants below are the ONLY threshold-shaped literals in
# this section; everything else derives from data every time it runs.
#
# UNLIKE `_dominance_band`'s deliberately-narrow 60-day "recent" window (built to catch the BAND
# ITSELF shifting), the percentile here is computed over the FULL trailing history available.
# The measured ~1.2/month figure was priced against that full-history population — a narrow
# recent window would be reactive (today's own spike inflates tomorrow's bar) and would quietly
# re-argue a number the operator has already priced and accepted. "Recomputed every run" means
# the population GROWS as more days of `mi_daily_closes` arrive, not that it's windowed to a
# fixed recent slice.
#
# "30-SESSION", not "30-day": the move is measured as an INDEX offset of 30 trading entries in
# each complex's own spread series (matching the #579 probe that produced the priced numbers),
# not a 30-calendar-day gap the way `_dominance_band`'s BTC-dominance series is windowed — the
# two series have different data-density reasons for that choice, not an inconsistency to fix.
_SPREAD_ALERT_PCTL = 75                       # measured 2026-09-11 (#579) — NOT 10 or 15pts; a PERCENTILE, recomputed fresh from data
_SPREAD_ALERT_MOVE_SESSIONS = 30              # the horizon #579 measured against, and the crypto lane's own horizon
_SPREAD_ALERT_WINDOW_BARS = _WINDOWS[0][1]    # 21 — the SAME 1M window the operator was shown, not a second constant
_SPREAD_ALERT_MIN_JUDGED = 240                # mirrors `_DOM_BASELINE_DAYS` — below this a percentile is too noisy to trust; SKIP rather than guess a bar

# Only complexes with BOTH an anchor and an equity expression can carry a direction spread at
# all (#579 DoD 6) — Uranium/Agriculture/Macro backdrop have no `senior`/`junior` legs paired
# with an anchor and must be ABSENT from this alert, never silently counted as quiet. Plain-word
# labels for the message (DoD 4: "gold miners pulling ahead of gold", not "Precious metals
# spread +14.9").
_SPREAD_ALERT_LABELS: dict[str, dict[str, str]] = {
    "Precious metals": {"anchor": "gold", "expression": "gold miners"},
    "Energy": {"anchor": "oil & gas", "expression": "energy stocks"},
}
_SPREAD_ALERT_COMPLEXES: tuple[str, ...] = tuple(_SPREAD_ALERT_LABELS)


def _percentile(xs: list[float], p: float) -> float | None:
    """Linear-interpolation percentile (numpy's default 'linear' method), no numpy dependency.
    `p` in [0, 100]."""
    if not xs:
        return None
    s = sorted(xs)
    n = len(s)
    if n == 1:
        return s[0]
    k = (p / 100.0) * (n - 1)
    lo = int(k)
    hi = min(lo + 1, n - 1)
    frac = k - lo
    return s[lo] + (s[hi] - s[lo]) * frac


def _returns_by_date(closes: list[tuple[date, float]], bars: int) -> dict[date, float]:
    """{date: trailing %return over `bars` of THIS ticker's own trading days} — the same
    definition `_ret` uses for "today", computed at every point instead of only the latest so
    a full history can be walked."""
    out: dict[date, float] = {}
    for i in range(bars, len(closes)):
        prev = closes[i - bars][1]
        if prev != 0:
            out[closes[i][0]] = (closes[i][1] / prev - 1.0) * 100.0
    return out


def _basket_returns_by_date(series: dict[str, list[tuple]], tickers: list[str],
                             bars: int) -> dict[date, float]:
    """Equal-weighted basket return at every date ANY member has enough history — the same
    drop-the-short-leg rule `_basket` uses for "today", generalised across the whole series."""
    per_ticker = [_returns_by_date(series.get(t, []), bars) for t in tickers]
    all_dates: set = set().union(*per_ticker) if per_ticker else set()
    out: dict[date, float] = {}
    for d in all_dates:
        vals = [m[d] for m in per_ticker if d in m]
        if vals:
            out[d] = sum(vals) / len(vals)
    return out


def _direction_spread_series(series: dict[str, list[tuple]], complex_def: dict,
                              bars: int) -> list[tuple[date, float]]:
    """(date, spread) oldest-first for one complex — expression minus anchor, the exact
    quantity `compute_strength_map` shows for "today" (`windows[w]["spread"]`), computed at
    every date instead of just the latest so #579's alert can measure its own history. Joined
    by DATE (not raw list position) so a ticker with a different data start date can never
    silently misalign the series."""
    anchor = _basket_returns_by_date(series, complex_def["anchor"], bars)
    expr = _basket_returns_by_date(series, complex_def["senior"] + complex_def["junior"], bars)
    dates = sorted(set(anchor) & set(expr))
    return [(d, expr[d] - anchor[d]) for d in dates]


def _signed_session_moves(spread_hist: list[tuple[date, float]],
                           n_sessions: int = _SPREAD_ALERT_MOVE_SESSIONS
                           ) -> list[tuple[date, float]]:
    """(date, SIGNED change in spread) over the prior `n_sessions` trading sessions. A positive
    move means the equity expression gained ground on the anchor over that stretch; negative
    means it lost ground — the sign IS the direction. #579: *"what about the reverse — what if
    it drops ten points?"* — a fall is measured exactly like a rise (the magnitude gate below
    is symmetric); only the message differs."""
    return [(spread_hist[i][0], spread_hist[i][1] - spread_hist[i - n_sessions][1])
            for i in range(n_sessions, len(spread_hist))]


def _classify_spread_state(move_signed: float, band: float) -> str:
    """'pulling_ahead' (expression gained on the anchor by AT OR ABOVE the band — #579 DoD 2:
    "the move goes from below the bar to AT OR ABOVE it"), 'falling_behind' (lost by at/above
    the band), or 'quiet' (inside the band — no direction earned)."""
    if move_signed >= band:
        return "pulling_ahead"
    if move_signed <= -band:
        return "falling_behind"
    return "quiet"


def _is_new_crossing(old_state: str, new_state: str) -> bool:
    """#579 DoD 2+3 — the entire dedupe. Fire ONLY on a genuine crossing (into a non-quiet
    state that differs from what was last persisted): a same-direction hold is one event, not
    one per day it stays above (median run is 2-3 days — firing daily is the exact failure mode
    named in the task); dropping back to 'quiet' fires nothing but clears the dedupe so the SAME
    direction can fire again later; a direct flip to the OPPOSITE direction always fires — a
    +10-through-zero-to-−10 swing is two different trades, not one continuing event."""
    return new_state != "quiet" and new_state != old_state


def _crossings_per_month(dated_moves: list[tuple[date, float]], band: float) -> float:
    """#579 DoD 5 — the silence rate stated ON the alert itself, so a quiet month is provably
    "nothing happened" rather than "the job died". Walks the WHOLE trailing history against
    THIS run's freshly-recomputed band (not walk-forward re-percentiled at every step — that
    would be a second, more expensive measurement the operator has not priced) and counts
    genuine `_is_new_crossing` events, per direction, over the elapsed span."""
    if not dated_moves:
        return 0.0
    state = "quiet"
    events = 0
    for _, mv in dated_moves:
        new_state = _classify_spread_state(mv, band)
        if _is_new_crossing(state, new_state):
            events += 1
        state = new_state
    span_days = (dated_moves[-1][0] - dated_moves[0][0]).days
    if span_days <= 0:
        return 0.0
    return round(events / (span_days / 30.44), 1)


def evaluate_spread_crossing(spread_hist: list[tuple[date, float]], old_state: str) -> dict:
    """PURE core (#579) — no I/O. Given one complex's full (date, spread) history and its last
    PERSISTED alert state, decides whether the latest reading is a new crossing and returns
    everything the message + audit row need. The DB-bound orchestrator
    (`run_spread_crossing_alert`) is a thin I/O wrapper around this function; every dedupe rule
    lives here and is tested here without a database."""
    dated_moves = _signed_session_moves(spread_hist)
    if len(dated_moves) < _SPREAD_ALERT_MIN_JUDGED:
        return {"measured": False, "judged": len(dated_moves)}
    band = _percentile([abs(m) for _, m in dated_moves], _SPREAD_ALERT_PCTL)
    today_date, today_move = dated_moves[-1]
    new_state = _classify_spread_state(today_move, band)
    return {
        "measured": True,
        "judged": len(dated_moves),
        "date": today_date,
        "band": round(band, 2),
        "move": round(today_move, 2),
        "spread_now": round(spread_hist[-1][1], 2) if spread_hist else None,
        "old_state": old_state,
        "new_state": new_state,
        "crossed": _is_new_crossing(old_state, new_state),
        "crossings_per_month": _crossings_per_month(dated_moves, band),
    }


def format_spread_crossing_alert(complex_name: str, ev: dict) -> str:
    """Telegram text for one crossing event. #579 DoD 4 — the message MUST name the DIRECTION
    in plain words ("gold miners pulling ahead of gold" / "gold miners falling behind gold");
    an absolute-value trigger would render opposite trades identically, which is the defect
    this whole surface exists to fix. DoD 5 — states its own silence rate on the same message.
    Monospace code block for the numbers, no pipe tables (CLAUDE.md Telegram formatting)."""
    labels = _SPREAD_ALERT_LABELS[complex_name]
    anchor, expr = labels["anchor"], labels["expression"]
    expr_cap = expr[0].upper() + expr[1:]
    if ev["new_state"] == "pulling_ahead":
        headline = f"{expr_cap} pulling ahead of {anchor}"
    else:
        headline = f"{expr_cap} falling behind {anchor}"
    spread_now = ev.get("spread_now")
    if spread_now is None:
        gap_line = "current 1-month gap: not computed"
    else:
        who, other = (expr, anchor) if spread_now > 0 else (anchor, expr)
        gap_line = f"current 1-month gap: {who} ahead of {other} by {abs(spread_now):.1f}pts"
    out = [
        f"🗺 *Strength map — {complex_name}*",
        headline,
        "```",
        f"30-session move: {ev['move']:+.1f}pts  (bar: {ev['band']:.1f}pts — this pair's own "
        f"75th percentile, recalculated today)",
        gap_line,
        "```",
        f"_Fires about {ev['crossings_per_month']:.1f}x a month for this pair — quiet the rest "
        f"of the time · a READ, not a rule_",
    ]
    return "\n".join(out)


_SPREAD_ALERT_STATE_TABLE = "mi_strength_spread_alert_state"


async def _get_alert_state(conn, complex_name: str) -> str:
    row = await conn.fetchrow(
        f"SELECT state FROM {_SPREAD_ALERT_STATE_TABLE} WHERE complex_name = $1", complex_name)
    return row["state"] if row else "quiet"


async def _set_alert_state(conn, complex_name: str, state: str,
                            move: float | None, band: float | None) -> None:
    await conn.execute(
        f"""
        INSERT INTO {_SPREAD_ALERT_STATE_TABLE}
            (complex_name, state, last_move, last_band, updated_at)
        VALUES ($1, $2, $3, $4, NOW())
        ON CONFLICT (complex_name) DO UPDATE
        SET state = EXCLUDED.state, last_move = EXCLUDED.last_move,
            last_band = EXCLUDED.last_band, updated_at = NOW()
        """, complex_name, state, move, band)


async def run_spread_crossing_alert(today: date) -> dict:
    """#579 — the ad-hoc alert on the strength-map direction spreads. THE LINE: notification
    only — no strategy, entry, exit, sizing, safeguard, grade or admission is touched anywhere
    in this function.

    Scheduled DAILY, after `ingest_daily` has refreshed `mi_daily_closes` — the input is daily
    CLOSES, so this is the earliest hour the reading can honestly be said to have changed (no
    intraday read is implied or attempted).

    Only `_SPREAD_ALERT_COMPLEXES` (Precious metals, Energy) are evaluated — DoD 6: Uranium,
    Agriculture and Macro backdrop have no anchor+expression pair and are absent, not silently
    treated as quiet.

    Per complex: reads the persisted last-alert state, computes the full spread history, and
    Telegrams ONLY when `evaluate_spread_crossing` reports a genuine crossing. State is
    persisted only AFTER a successful Telegram send — a delivery failure leaves the OLD state
    in place, so the next run's comparison naturally retries the same crossing instead of
    silently eating it. An `mi_audit_log` row is written every run a band could be measured
    (so the series is graphable even on quiet days), matching `book_concentration`'s
    audit-always/Telegram-only-when-flagged house rule.

    One complex's failure is caught and logged (`# loud-ok:`) so it can never block the other
    complex or break the host job; a genuinely systemic failure (e.g. the DB read itself) still
    propagates to the caller, which the scheduler wraps in `audit_wrap` + `notify_job_failure`
    like every other job in this file."""
    pool = await get_pool()
    tickers = sorted({t for name in _SPREAD_ALERT_COMPLEXES
                       for c in COMPLEXES if c["name"] == name
                       for k in ("anchor", "senior", "junior") for t in c[k]})
    fired: list[str] = []
    skipped: list[str] = []
    errors: list[str] = []
    async with pool.acquire() as conn:
        rows = await conn.fetch(_CLOSES_SQL, tickers, today)
        series: dict[str, list[tuple]] = {}
        for r in rows:
            series.setdefault(r["ticker"], []).append((r["trade_date"], float(r["close"])))
        for c in COMPLEXES:
            if c["name"] not in _SPREAD_ALERT_COMPLEXES:
                continue
            try:
                spread_hist = _direction_spread_series(series, c, _SPREAD_ALERT_WINDOW_BARS)
                old_state = await _get_alert_state(conn, c["name"])
                ev = evaluate_spread_crossing(spread_hist, old_state)
                if not ev["measured"]:
                    skipped.append(c["name"])
                    logger.info(
                        f"strength spread alert: {c['name']} insufficient history "
                        f"({ev['judged']} judged days, need {_SPREAD_ALERT_MIN_JUDGED}) — "
                        "skipped, no default guessed")
                    continue
                await log_audit_event(
                    "strength_spread_alert_check",
                    summary=(f"{c['name']}: state={ev['new_state']} move={ev['move']:+.1f} "
                             f"band={ev['band']:.1f} crossed={ev['crossed']}"),
                    detail=json.dumps({**ev, "date": str(ev["date"]), "complex": c["name"]}),
                )
                if ev["crossed"]:
                    from agents.market_intelligence.briefing import send_telegram_message
                    ok = await send_telegram_message(
                        format_spread_crossing_alert(c["name"], ev))
                    # `send_telegram_message` returns False (does NOT raise) on a missing
                    # token/chat-id or an HTTP failure — the state write below must be SKIPPED
                    # on that path, or the crossing is silently eaten: tomorrow's comparison
                    # would see the OLD (unfired) state and never notice it already changed.
                    if not ok:
                        logger.warning(
                            f"strength spread alert: Telegram send failed for {c['name']} — "
                            "state NOT advanced, next run will retry this crossing")
                        errors.append(c["name"])
                        continue
                    fired.append(c["name"])
                await _set_alert_state(conn, c["name"], ev["new_state"], ev["move"], ev["band"])
            except Exception as e:  # loud-ok: one complex's data/send problem must not silence the other complex or break the host job
                logger.warning(f"strength spread alert failed for {c['name']}: {e}")
                errors.append(c["name"])
    return {"fired": fired, "skipped": skipped, "errors": errors}
