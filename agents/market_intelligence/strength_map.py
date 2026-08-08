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

import logging
from datetime import date
from typing import Any

from agents.market_intelligence.db import get_pool

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
