"""#713 — the `/why` SCORE section: HOW an EP score was built, in plain words.

DISPLAY ONLY. Reads one stored `mi_ep_scan_log` row and the live rubric table
(`ep_rubric.SCORE_WEIGHTS`, or `SCORE_WEIGHTS_LEGACY` for a row stamped
`score_side='legacy'`) and prints each part with its points and what the NEXT tier of that
part would pay, the raw total, the regime multiplier, the #533 presentation rescale and the
distance to the HIGH bar in RAW points. It changes no score, bar, tier or weight, and reads
every tier cut and point value from the table — a number typed in here would drift the day
the table is re-tuned.

Why it exists (operator 2026-10-29): FTAI scored 61.2 under a bar of 65 and neither `/setup`
nor `/why` showed how the 61.2 was reached. The stored breakdown is the RAW parts (they do not
sum to the presented score: the regime multiplier and the rescale sit outside it).

The regime multiplier is NOT stored on the scan row (`ep_decision_vector` marks it derived from
the regime record), so it is worked back from the stored score by inverting the rescale — the
same inversion `health_checks._lattice_prevented_alerts` uses — and labelled "worked back".
Today the agreement boost is retired (#233), so the only live values are x1.0 and the Bull-day
x1.2; an older row can carry a product of the two.

Plain text, no Markdown, no pipe table: `/why` posts with no parse_mode (see
`_format_catalyst_grade_block`).
"""
from __future__ import annotations

import json
from typing import Any

from agents.market_intelligence.ep_rubric import (
    SCORE_WEIGHTS, SCORE_WEIGHTS_LEGACY, SEPARATION_BAR, apply_output_scale,
    resolve_conviction_floor, tier_points,
)

# Display order of the parts. Anything else in a stored breakdown (an older row's axes) is
# rendered after these, by name, with no next-tier text — never dropped, because the raw total
# must still add up to what the row says.
_ORDER = ("gap", "liquidity", "catalyst", "float", "vol_conviction", "theme_bonus",
          "conviction_floor")
_LABEL = {
    "gap": "gap", "liquidity": "liquidity", "catalyst": "catalyst", "float": "float",
    "vol_conviction": "pre-market volume", "theme_bonus": "theme",
    "conviction_floor": "conviction floor",
}
_GRADE_FALLBACK = {"game_changer": "game-changing", "strong": "strong", "routine": "routine",
                   "mna": "merger/acquisition"}


def _grade_words(quality: Any) -> str:
    """The operator's words for a catalyst grade (one source: briefing.format_catalyst_grade;
    the local map is only the fallback if that import ever fails in a slim runtime)."""
    q = (str(quality) if quality is not None else "").strip()
    if not q:
        return "no grade"
    try:
        from agents.market_intelligence.briefing import format_catalyst_grade
        return format_catalyst_grade(q) or q
    except Exception:   # loud-ok: display-only wording fallback
        return _GRADE_FALLBACK.get(q, q.replace("_", " "))


def _num(v: Any) -> float | None:
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def _pt(v: Any) -> str:
    """Signed points, no trailing .0: 10 -> '+10', 0 -> '+0', -5 -> '-5'."""
    f = _num(v) or 0.0
    return f"{int(f):+d}" if f == int(f) else f"{f:+.1f}"


def _money(v: float) -> str:
    return f"${v / 1e9:g}B" if v >= 1e9 else f"${v / 1e6:g}M"


def _ordinal(v: float) -> str:
    n = int(v)
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _next_tier(points: float, tiers: list) -> tuple[float, float] | None:
    """The tier that pays the NEAREST amount above `points` (None at the top)."""
    above = [(t, p) for t, p in tiers if p > points]
    return min(above, key=lambda tp: tp[1]) if above else None


def _current_tier(points: float, tiers: list) -> tuple[float, float] | None:
    return next(((t, p) for t, p in tiers if p == points), None)


def _ladder(points: float, tiers: list, fmt) -> tuple[str, str]:
    """(this-tier phrase, next-tier phrase) for a descending `(threshold, points)` ladder."""
    cur = _current_tier(points, tiers)
    if cur is not None:
        here = f"{fmt(cur[0])} or more"
    else:
        here = "below the lowest tier"
    nxt = _next_tier(points, tiers)
    there = f"next tier {fmt(nxt[0])} pays {_pt(nxt[1]).lstrip('+')}" if nxt else "top tier"
    return here, there


def _weights_for(score_side: Any) -> dict:
    return SCORE_WEIGHTS_LEGACY if str(score_side or "").lower() == "legacy" else SCORE_WEIGHTS


def _breakdown_of(raw: Any) -> dict | None:
    """The JSONB column arrives as a dict through the pool's codec; a raw string is cheap
    insurance, a malformed one reads as 'no breakdown'."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError):
            return None
    return raw if isinstance(raw, dict) and raw else None


def _component_line(key: str, pts: float, row: dict, w: dict) -> str:
    """One part: `<label> <points>  <why this much> · <what the next tier pays>`."""
    label = _LABEL.get(key, key.replace("_", " "))
    head = f"   {label} {_pt(pts)}  "

    if key == "gap":
        cfg = w["gap"]
        here, there = _ladder(pts, cfg["tiers"], lambda t: f"{t:g}%")
        g = _num(row.get("gap_pct"))
        seen = f"{g:.1f}% gap — " if g is not None else ""
        if len(cfg["tiers"]) == 1 and not _next_tier(pts, cfg["tiers"]):
            there = "flat credit, a bigger gap pays nothing more"
        return head + f"{seen}{here} · {there}"

    if key == "liquidity":
        cfg = w["liquidity"]
        adv, pc = _num(row.get("adv")), _num(row.get("prev_close"))
        adv_dollar = adv * pc if adv and pc and adv > 0 and pc > 0 else None
        if adv_dollar is not None and tier_points(
                adv_dollar, cfg["adv_tiers"], cfg["adv_default"]) == pts:
            here, there = _ladder(pts, cfg["adv_tiers"], _money)
            return head + f"average daily dollar volume {_money(adv_dollar)} — {here} · {there}"
        signal = _num(row.get("projected_vol_multiple"))
        signal = signal if signal is not None else _num(row.get("rel_volume"))
        if signal is not None and tier_points(
                signal, cfg["fallback_tiers"], cfg["fallback_default"]) == pts and adv_dollar is None:
            here, there = _ladder(pts, cfg["fallback_tiers"], lambda t: f"{t:g}x")
            return (head + f"average dollar volume unknown, priced off today's volume "
                    f"{signal:.1f}x normal — {here} · {there}")
        here, there = _ladder(pts, cfg["adv_tiers"], _money)
        return head + f"average daily dollar volume {here} · {there}"

    if key == "catalyst":
        cfg = w["catalyst"]
        q = row.get("catalyst_quality")
        grade_pts = cfg["points"]
        nxt = min(((g, p) for g, p in grade_pts.items() if p > pts),
                  key=lambda gp: gp[1], default=None)
        there = (f"next grade up: {_grade_words(nxt[0])} pays {_pt(nxt[1]).lstrip('+')}"
                 if nxt else "top grade")
        return head + f"graded {_grade_words(q)} · {there}"

    if key == "float":
        cfg = w["float"]
        fs = _num(row.get("float_shares"))
        cap = f"{cfg['max_shares'] / 1e6:g}M"
        seen = f"{fs / 1e6:.0f}M shares — " if fs and fs > 0 else ""
        if pts:
            return head + f"{seen}under {cap} shares · top tier"
        return head + (f"{seen}not under {cap} shares · under {cap} pays "
                       f"{_pt(cfg['points']).lstrip('+')}")

    if key == "vol_conviction":
        cfg = w["vol_conviction"]
        vp = _num(row.get("vol_percentile"))
        here, there = _ladder(pts, cfg["tiers"], lambda t: f"{_ordinal(t)} percentile")
        seen = (f"at its own {_ordinal(vp)} percentile — "
                if vp is not None else "")
        return head + f"{seen}{here} · {there}"

    if key == "theme_bonus":
        cfg = w["theme_bonus"]
        if pts:
            return head + "in a paying theme · top tier"
        return head + f"not in a paying theme · a paying theme pays {_pt(cfg['points']).lstrip('+')}"

    if key == "conviction_floor":
        gap, q = _num(row.get("gap_pct")), row.get("catalyst_quality")
        rule = None
        if gap is not None and q is not None:
            floor = resolve_conviction_floor(gap, q, w["conviction_floor"]["rules"])
            rule = next((r for r in w["conviction_floor"]["rules"]
                         if r["floor"] == floor and gap >= r["min_gap"]
                         and q == r["catalyst"]), None)
        if rule and not pts:
            return head + (f"a {_grade_words(rule['catalyst'])} catalyst on a gap of "
                           f"{rule['min_gap']:g}% or more has a floor of {rule['floor']:g}; "
                           f"the parts already total more, so it lifted nothing")
        if rule:
            return head + (f"a {_grade_words(rule['catalyst'])} catalyst on a gap of "
                           f"{rule['min_gap']:g}% or more lifts the raw total to at least "
                           f"{rule['floor']:g}")
        return head + "lifts the raw total up to a floor set by the catalyst and the gap"

    return head + "(not in the current score table)"


def _mult_label(m: float) -> str:
    # Mirrors ep_detector: x1.2 on a Bull day, x1.0 otherwise (the retired agreement boost
    # #233 is pinned at 1.0; an older row can carry the product of the two).
    if abs(m - 1.0) < 0.005:
        return "no regime boost"
    if abs(m - 1.2) < 0.005:
        return "Bull-day boost"
    return "regime and older agreement boosts combined"


def _raw_needed(mult: float, bar: float, scale: dict | None) -> int | None:
    """Smallest whole raw total that presents at or above `bar` under `mult` — the same
    arithmetic as the scorer (round(raw x mult, 1), then the rescale), searched, not inverted,
    so rounding at the boundary is whatever the scorer would do."""
    if mult <= 0:
        return None
    for r in range(0, 1001):
        if apply_output_scale(round(r * mult, 1), scale) >= bar:
            return r
    return None


def score_math_lines(row: dict | None) -> list[str]:
    """The `/why` SCORE section for one `mi_ep_scan_log` row, as plain-text lines.

    `row` keys used (all optional except what is named): ep_score + score_breakdown (the two
    that make a section at all), score_side, ep_bar, catalyst_quality, gap_pct, adv, prev_close,
    projected_vol_multiple, rel_volume, float_shares, vol_percentile, and `scan_time_et` (a
    datetime, for the header). Returns [] for no row (the caller extends unconditionally).
    A row with no stored breakdown says so plainly rather than going silent."""
    if not row:
        return []
    ep_score = _num(row.get("ep_score"))
    breakdown = _breakdown_of(row.get("score_breakdown"))
    when = ""
    t = row.get("scan_time_et")
    if t is not None:
        try:
            from agents.market_intelligence.collector import _ET
            when = f" ({t.astimezone(_ET).strftime('%H:%M')} ET scan)"
        except Exception:   # loud-ok: a clock quirk drops the time, never the section
            when = ""
    if breakdown is None:
        shown = f"{ep_score:.1f}" if ep_score is not None else "no score"
        return ["", f"🧮 SCORE — {shown}{when}: the score parts were not stored for this "
                    "row (scored before 2026-08-29, or killed before scoring)"]

    w = _weights_for(row.get("score_side"))
    legacy = w is SCORE_WEIGHTS_LEGACY
    scale = w.get("output_scale")
    parts = {k: _num(v) or 0.0 for k, v in breakdown.items()}
    raw = sum(parts.values())

    body: list[str] = []
    for key in list(_ORDER) + sorted(k for k in parts if k not in _ORDER):
        if key in parts:
            body.append(_component_line(key, parts[key], row, w))
    body.append(f"   raw total {_pt(raw).lstrip('+')}")

    # Regime multiplier, worked back from the stored score (not stored on the row).
    mult: float | None = None
    if ep_score is not None and raw > 0:
        final = (round((ep_score - scale["offset"]) / scale["mult"], 1) if scale else ep_score)
        mult = final / raw
    final_shown: float | None = None
    if mult is None:
        body.append("   regime multiplier: not shown — "
                    + ("the raw total is 0, so there is nothing to multiply"
                       if ep_score is not None else "no stored score to work it back from"))
    else:
        final_shown = round(raw * mult, 1)
        body.append(f"   x{mult:.2f} regime multiplier ({_mult_label(mult)}; worked back from "
                    f"the stored score) = {final_shown:g}")
        if scale:
            presented = apply_output_scale(final_shown, scale)
            body.append(
                f"   rescale {scale['mult']:g} x {final_shown:g} + {scale['offset']:g} = "
                f"{presented:g}  (a display step only: the bar goes through the same step)")
            if ep_score is not None and abs(presented - ep_score) > 0.05:
                body.append(f"   does NOT reconcile: rebuilt {presented:g}, stored {ep_score:g}")
        else:
            body.append("   no rescale on this row (old raw scale)")

    # Distance to the bar, in RAW points.
    bar = _num(row.get("ep_bar"))
    if bar is None and not legacy:
        bar = float(SEPARATION_BAR)
    verdict = ""
    need: int | None = None
    if bar is not None and mult is not None:
        need = _raw_needed(mult, bar, scale)
        if need is None:
            body.append(f"   the HIGH bar is {bar:g}; the raw total needed could not be worked out")
        else:
            under = need - raw
            pre = f" (= {(bar - scale['offset']) / scale['mult']:g} before the rescale)" if scale else ""
            times = (f" ({need} x {mult:.2f} = {round(need * mult, 1):g})"
                     if abs(mult - 1.0) > 0.005 else "")
            at = f"needs a raw total of {need}{times}; this has {_pt(raw).lstrip('+')}"
            if under > 0:
                verdict = (f", {_pt(under).lstrip('+')} raw point{'s' if under != 1 else ''} "
                           f"short of the HIGH bar {bar:g}")
                body.append(f"   HIGH bar {bar:g}{pre} {at}")
            else:
                verdict = f", clears the HIGH bar {bar:g}"
                body.append(f"   HIGH bar {bar:g}{pre} {at} ({_pt(raw - need).lstrip('+')} to spare)")
    elif bar is not None:
        verdict = f", HIGH bar {bar:g}"

    # A sub-bar name with no theme points: say plainly when the theme points ALONE would have
    # cleared the bar (the FTAI 10-29 question). Same arithmetic as the scorer, one input moved.
    tpts = _num((w.get("theme_bonus") or {}).get("points"))
    if (mult is not None and bar is not None and "theme_bonus" in parts
            and not parts["theme_bonus"] and tpts and need is not None and raw < need):
        if raw + tpts >= need:
            alt = apply_output_scale(round((raw + tpts) * mult, 1), scale)
            body.append(f"   with the theme points ({_pt(tpts)} raw) it would have scored "
                        f"{alt:g}, over the bar")

    head = f"🧮 SCORE — {ep_score:.1f}" if ep_score is not None else "🧮 SCORE — no score"
    return ["", head + verdict + when] + body


# ── The SHORT form (#716): each part OUT OF its maximum ──────────────────────────────────────
# Display order of the short parts line (the operator-approved mockup order — it differs from
# `_ORDER`, which is the long section's order and stays as it is).
_SHORT_ORDER = ("gap", "liquidity", "catalyst", "theme_bonus", "float", "vol_conviction")


def part_maxima(w: dict) -> dict[str, float]:
    """The most each ADDITIVE score part can pay, READ from the weights table `w` — never typed,
    so a re-tuned table moves the "out of" figures with it. Takes the table as an argument because
    the two sides differ (the legacy gap ladder tops out at 25, the live flat credit at 10).
    `conviction_floor` is not here: it is a lift to a floor, not a part with a ceiling."""
    out: dict[str, float] = {}
    gap = w.get("gap")
    if gap and gap.get("tiers"):
        out["gap"] = max(p for _, p in gap["tiers"])
    liq = w.get("liquidity")
    if liq:
        out["liquidity"] = max([p for _, p in liq.get("adv_tiers", [])]
                               + [p for _, p in liq.get("fallback_tiers", [])] + [0])
    cat = w.get("catalyst")
    if cat and cat.get("points"):
        out["catalyst"] = max(cat["points"].values())
    flt = w.get("float")
    if flt and flt.get("points") is not None:
        out["float"] = flt["points"]
    vol = w.get("vol_conviction")
    if vol and vol.get("tiers"):
        out["vol_conviction"] = max(p for _, p in vol["tiers"])
    theme = w.get("theme_bonus")
    if theme and theme.get("points") is not None:
        out["theme_bonus"] = theme["points"]
    return out


def _g(v: float) -> str:
    return f"{v:g}"


def score_short_lines(row: dict | None) -> list[str]:
    """The SHORT `/why` score lines for one `mi_ep_scan_log` row: every part as `points/maximum`,
    the raw total against the raw total possible and the HIGH bar in RAW points, and what each
    part still below its maximum could add. Three lines at most, each indented three spaces.

    DISPLAY ONLY, same inputs and same arithmetic as `score_math_lines` (the long section) — the
    bar in raw points is the smallest raw total that presents at or above the bar under the
    regime multiplier worked back from the stored score. Returns [] for no row / no stored parts
    (the caller says so in its own words); a part the breakdown does not carry is not shown, so
    "of N" only counts the parts that were actually scored."""
    if not row:
        return []
    breakdown = _breakdown_of(row.get("score_breakdown"))
    if breakdown is None:
        return []
    w = _weights_for(row.get("score_side"))
    legacy = w is SCORE_WEIGHTS_LEGACY
    scale = w.get("output_scale")
    parts = {k: _num(v) or 0.0 for k, v in breakdown.items()}
    maxima = part_maxima(w)
    raw = sum(parts.values())

    shown: list[str] = []
    for key in _SHORT_ORDER:
        if key in parts and key in maxima:
            shown.append(f"{_LABEL.get(key, key)} {_g(parts[key])}/{_g(maxima[key])}")
    lift = parts.get("conviction_floor", 0.0)
    if lift:
        shown.append(f"floor lift +{_g(lift)}")
    for key in sorted(k for k in parts if k not in _SHORT_ORDER and k != "conviction_floor"):
        shown.append(f"{_LABEL.get(key, key.replace('_', ' '))} {_g(parts[key])}")
    out = ["   " + " · ".join(shown)]

    possible = sum(maxima[k] for k in _SHORT_ORDER if k in parts and k in maxima)
    total = f"raw {_g(raw)} of {_g(possible)}"

    # Bar in RAW points: the same search the long section uses.
    ep_score = _num(row.get("ep_score"))
    mult: float | None = None
    if ep_score is not None and raw > 0:
        final = round((ep_score - scale["offset"]) / scale["mult"], 1) if scale else ep_score
        mult = final / raw
    bar = _num(row.get("ep_bar"))
    if bar is None and not legacy:
        bar = float(SEPARATION_BAR)
    need = _raw_needed(mult, bar, scale) if (mult is not None and bar is not None) else None
    if need is None:
        out.append("   " + total + (f" · HIGH bar {_g(bar)}" if bar is not None else ""))
    else:
        gap_pts = raw - need
        if gap_pts > 0:
            tail = f"{_g(gap_pts)} to spare"
        elif gap_pts < 0:
            tail = f"{_g(-gap_pts)} short"
        else:
            tail = "exactly on the bar"
        boost = (f" ({_mult_label(mult)}, x{mult:.2f})" if abs(mult - 1.0) > 0.005 else "")
        out.append(f"   {total} · HIGH bar {need}{boost} · {tail}")

    room = [f"{_LABEL.get(k, k)} +{_g(maxima[k] - parts[k])}"
            for k in _SHORT_ORDER
            if k in parts and k in maxima and parts[k] < maxima[k]]
    if room:
        out.append("   could still add: " + " · ".join(room))
    return out


# ── The theme read (the +10 a name did NOT get) ──────────────────────────────────────────────
_NO_VERDICT = {
    "failed": "the fit check failed", "timeout": "the fit check timed out",
    "error": "the fit check errored", "budget": "the day's fit-check budget was used up",
    "off": "the belonging check is switched off", "window": "it ran outside the pre-market window",
    "no_description": "there was no company description to judge", "pending": "the fit check was still pending",
    "no_read": "no belonging read was taken",
}


def _cap(txt: str, n: int) -> str:
    return txt if len(txt) <= n else txt[:n].rsplit(" ", 1)[0] + "…"


def _first_shortlisted(shadow: dict) -> tuple[str | None, str | None, float | None]:
    raw = shadow.get("shortlist")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError):
            raw = None
    if isinstance(raw, list) and raw and isinstance(raw[0], dict):
        r0 = raw[0]
        return r0.get("theme"), r0.get("stage"), _num(r0.get("corr"))
    return None, None, None


def theme_read_lines(shadow: dict | None) -> list[str]:
    """One-to-three plain lines on WHY a name got no theme points, from its
    `mi_ep_theme_belonging_shadow` row (listed in a paying theme or not; the belonging check's
    best match and its verdict). Display only. `None` = no record for that day."""
    if not shadow:
        return ["   theme read: no belonging-check record for this name on this day"]
    if shadow.get("listed"):
        return ["   theme read: the name IS listed in a paying theme (the points come from the "
                "list)"]
    status = str(shadow.get("fit_status") or "")
    theme, stage, corr = _first_shortlisted(shadow)
    theme = theme or shadow.get("best_theme")
    stage = stage or shadow.get("best_stage")
    corr = corr if corr is not None else _num(shadow.get("best_corr"))
    match = (f"{theme} ({stage}, price co-movement {corr:.2f})"
             if theme and corr is not None else theme or "")
    if status == "rejected":
        why = (shadow.get("fit_rationale") or "").strip()
        out = [f"   theme read: not listed in a paying theme. The belonging check shortlisted "
               f"{match} and judged it NOT a fit, so no points"]
        if why:
            out.append(f"   its reason: \"{_cap(why, 180)}\"")
        return out
    if status == "confirmed":
        fit = shadow.get("fit_theme") or theme or "a paying theme"
        paid = ("and the points were paid" if shadow.get("acting_in_theme")
                else "but the belonging check was not acting, so no points were paid")
        return [f"   theme read: not listed, the belonging check judged it a fit for {fit} {paid}"]
    if status == "not_shortlisted":
        bar = _num(shadow.get("shortlist_bar"))
        under = f" (under the shortlist bar {bar:.2f})" if bar is not None else ""
        near = f"; closest was {match}{under}" if match else "; there was no paying-theme basket to compare"
        return [f"   theme read: not listed in a paying theme and no paying theme's stocks "
                f"moved with it{near}"]
    why = _NO_VERDICT.get(status, f"the fit check ended as '{status}'" if status else "no verdict was recorded")
    near = f"; closest match {match}" if match else ""
    return [f"   theme read: not listed in a paying theme, and {why}{near}"]
