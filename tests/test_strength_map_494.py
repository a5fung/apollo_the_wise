"""The strength map — asset vs the stocks that express it (#494 slice 2). READ-ONLY.

Operator ruled the design fork on 2026-08-08: **GROUP them into complexes.** A precious-metals
move shows up in BOTH gold and the miners, and the relationship between them is the signal.

Then he added the second axis, and it is the part these tests protect hardest:

> *"maybe there's sub splits on market cap for example, works for crypto as well, if smaller caps
> rise faster which is expected in a bull market with more risk taking, ppl going further into
> riskier spectrum, this is info. In crypto world, this is called alt season."*

So a complex has TWO readings — DIRECTION (stocks vs asset) and RISK APPETITE (juniors vs
seniors) — and the failure mode is quietly losing the second one.
"""
from datetime import date

from agents.market_intelligence.strength_map import (
    COMPLEXES, _basket, _ret, format_strength_map)


def _series(vals):
    return {"X": vals}


def test_a_short_history_is_ABSENT_not_zero():
    """A missing return must never render as 0 — that reads as 'flat', which is a claim we have
    no basis for. This is the fabricated-signal rule in its smallest form."""
    assert _ret([1.0, 2.0], 21) is None
    assert _basket({}, ["GLD"], 21) is None


def test_a_basket_drops_the_short_leg_rather_than_going_dark():
    """One ticker with thin history must not blank the whole complex — but an entirely empty
    basket still returns None."""
    s = {"A": [100.0] * 30, "B": [1.0, 2.0]}
    assert _basket(s, ["A", "B"], 21) is not None
    assert _basket(s, ["B"], 21) is None


# ── the risk axis: the thing most likely to be silently lost ──────────────────────────────

def test_the_risk_pair_is_only_claimed_where_it_is_REAL():
    """GDX/GDXJ is senior-vs-junior miners; XLE/XOP is majors-vs-E&P. Both are genuine size
    splits. Uranium, agriculture and the macro row have no honest pair in what we hold, and
    inventing one from two ETFs that differ by METAL rather than SIZE would be a fabricated
    signal — worse than a missing one."""
    by_name = {c["name"]: c for c in COMPLEXES}
    assert by_name["Precious metals"]["senior"] == ["GDX"]
    assert by_name["Precious metals"]["junior"] == ["GDXJ"]
    assert by_name["Energy"]["senior"] == ["XLE"]
    assert by_name["Energy"]["junior"] == ["XOP"]
    for name in ("Uranium", "Agriculture", "Macro backdrop"):
        assert not by_name[name]["junior"], (
            f"{name} claims a junior/senior split it does not honestly have")


def test_a_FLAT_risk_reading_is_still_SHOWN():
    """The bug this prevents: hiding the risk line when the number is small makes 'risk appetite
    is not moving' indistinguishable from 'we never computed it'. Both are silence; only one is
    true. Measured live on 08-07 the reading WAS flat (+0.2pts), so this is the normal case."""
    data = {"complexes": [{
        "name": "Precious metals", "has_risk_pair": True,
        "windows": {w: {"anchor": 5.0, "expression": 6.0, "spread": 1.0, "risk": 0.2}
                    for w in ("1M", "3M", "6M")}}]}
    out = format_strength_map(data)
    assert "risk: flat" in out and "+0.2" in out, out


def test_a_REAL_risk_move_is_named_in_words():
    data = {"complexes": [{
        "name": "Energy", "has_risk_pair": True,
        "windows": {w: {"anchor": 1.0, "expression": 9.0, "spread": 8.0, "risk": 6.0}
                    for w in ("1M", "3M", "6M")}}]}
    out = format_strength_map(data)
    assert "juniors" in out and "risk-ON" in out, out


def test_a_complex_with_NO_pair_shows_no_risk_line_at_all():
    """Not 'flat', not '0' — nothing. It has no size split, so it has no risk reading."""
    data = {"complexes": [{
        "name": "Uranium", "has_risk_pair": False,
        "windows": {w: {"anchor": None, "expression": 6.0, "spread": None, "risk": None}
                    for w in ("1M", "3M", "6M")}}]}
    assert "risk:" not in format_strength_map(data)


def test_alt_season_is_named_when_dominance_is_falling():
    """His word, kept in the output — it makes this one concept across every asset class rather
    than a crypto curiosity.

    ⚠ The trend is DERIVED here, not read from `crypto_btc_dominance.slope_30d`. That column is
    DEAD: 97 rows since 2026-04-27, every one NULL, because `crypto/ingest.py` only ever writes
    (date, dominance_pct, total_mcap_usd). The operator caught it on the very first render —
    *"why is btc 30 day trend missing? we've been shadowing for longer."* Reported as the CHANGE
    IN PERCENTAGE POINTS because "dominance fell 1.4pts in a month" is a sentence he can act on
    and a regression coefficient is not."""
    base = {"complexes": [{"name": "Energy", "has_risk_pair": False,
                           "windows": {w: {"anchor": 1.0, "expression": 1.0, "spread": 0.0,
                                           "risk": None} for w in ("1M", "3M", "6M")}}]}
    falling = dict(base, btc_dominance={"dominance_pct": 52.0, "change_30d": -1.4})
    assert "ALT SEASON" in format_strength_map(falling)
    rising = dict(base, btc_dominance={"dominance_pct": 60.0, "change_30d": 1.2})
    assert "BTC leading" in format_strength_map(rising)
    # 0.6pts is BELOW the measured median 30-day move (0.71) — it must NOT earn a direction.
    typical = dict(base, btc_dominance={"dominance_pct": 56.8, "change_30d": 0.6})
    out = format_strength_map(typical)
    assert "TYPICAL" in out and "leading" not in out.split("BTC dominance")[1], (
        "a move smaller than the typical 30-day move was labelled a direction — that is "
        "noise sold as signal, which is what the 0.5pt first guess did")


def test_short_dominance_history_says_so_instead_of_guessing():
    """The failure this replaces printed nothing and looked like a system fault. If we genuinely
    lack 30 days, say how much we have — never default to a direction."""
    base = {"complexes": [{"name": "Energy", "has_risk_pair": False,
                           "windows": {w: {"anchor": 1.0, "expression": 1.0, "spread": 0.0,
                                           "risk": None} for w in ("1M", "3M", "6M")}}]}
    thin = dict(base, btc_dominance={"dominance_pct": 56.8, "change_30d": None,
                                     "history_days": 12})
    out = format_strength_map(thin)
    assert "12d of history" in out and "need 30" in out, out
    assert "leading" not in out.split("BTC dominance")[1], (
        "a missing trend rendered as a direction — a NULL must never imply BTC or alts leading")


def test_it_does_not_read_the_dead_slope_column():
    """Regression guard: `slope_30d` has never once been populated. Reading it again would
    silently reinstate the blank the operator caught."""
    import pathlib as _pl
    src = _pl.Path("agents/market_intelligence/strength_map.py").read_text(encoding="utf-8")
    code = "\n".join(l.split("#", 1)[0] for l in src.split("\n"))
    assert "slope_30d" not in code, (
        "strength_map reads slope_30d again — that column is dead (97/97 NULL) and nothing "
        "writes it")


def test_the_dominance_band_is_CALIBRATED_not_guessed():
    """My first band was ±0.5pts, picked because it looked small. Measured against the 97 days
    we hold: the MEDIAN absolute 30-day change is 0.71pts (mean 1.12, range of the whole series
    3.36pts). A 0.5 band therefore called the median move a direction — noise as signal, roughly
    half the time. The band is now the median itself."""
    from agents.market_intelligence.strength_map import _DOM_TYPICAL_30D
    assert 0.6 <= _DOM_TYPICAL_30D <= 0.9, (
        f"dominance band {_DOM_TYPICAL_30D} is outside the measured typical move (~0.71pts) — "
        "re-measure before changing it")


def test_the_dominance_number_carries_its_SCALE():
    """0.8 sounds like nothing until you know the median 30-day move is 0.7 and the entire
    97-day range is 3.4 points. Operator asked "0.8 points is out of 100?" — the answer has to
    be on the surface, not in my head."""
    base = {"complexes": [{"name": "Energy", "has_risk_pair": False,
                           "windows": {w: {"anchor": 1.0, "expression": 1.0, "spread": 0.0,
                                           "risk": None} for w in ("1M", "3M", "6M")}}]}
    out = format_strength_map(dict(base, btc_dominance={"dominance_pct": 56.8,
                                                        "change_30d": 0.8}))
    assert "out of 100" in out and "typical 30d move" in out, out


def test_the_columns_line_up():
    """The first version used two different spacing recipes for the header and the data and the
    numbers collided (`+5.8+18.7-13.7`). Header and rows now share one helper."""
    data = {"complexes": [{
        "name": "Precious metals", "has_risk_pair": False,
        "windows": {w: {"anchor": 5.8, "expression": 18.7, "spread": 12.9, "risk": None}
                    for w in ("1M", "3M", "6M")}}]}
    lines = [l for l in format_strength_map(data).split("\n")
             if l and not l.startswith(("*", "`", "_")) and "lead" not in l]
    assert len({len(l.rstrip()) for l in lines}) <= 2, \
        "header and data rows are different widths again:\n" + "\n".join(lines)


def test_it_renders_NOTHING_when_there_is_nothing_to_say():
    assert format_strength_map({"complexes": []}) == ""
