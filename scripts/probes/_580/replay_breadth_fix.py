"""#580 replay — what the breadth-decay fix (A) and the birth-breadth fill (B) would have changed.

READ-ONLY, $0, no model calls. Run INSIDE the market container (the app's own DB pool; every query
runs in a READ ONLY transaction, so the server rejects any write):

    docker exec -i apollo-market python - < scripts/probes/_580/replay_breadth_fix.py \
        > /tmp/580_replay.jsonl 2> /tmp/580_replay_summary.txt

    # hand cases only, no DB (also runnable on a laptop):
    python3 scripts/probes/_580/replay_breadth_fix.py --selftest

stdout: one JSON line per CHANGED theme-day ({"kind": "theme_day", ...}) and per CHANGED EP alert
({"kind": "alert", ...}). stderr: the summary, including the replay's own fidelity checks.

THE CHANGE BEING REPLAYED (theme_engine._rescore_existing_theme, branch 580-breadth-decay-fix):
  (A) prior-night breadth read as `prev is not None and prev < 0.40` (was `(prev or 1.0) < 0.40`, so
      a stored 0.0 counted as healthy and the theme could never be forced Fading);
  (B) a theme is born WITH breadth (was NULL until its first rescore — so the next night's rule had
      no prior reading). Engine births: the engine's own date. Promote/seed births: the latest
      COMPLETE score run (#554 bar) at the time of the write.

METHOD (fixed before running):
  1. mi_themes from 2026-07-24 (history from 07-16 so the 7-day window is warm). For each RESCORE row
     (a prior non-Retired row of the same name within 7 days, breadth stored), recompute the stage
     with the engine's own rule TWICE: OLD = stored prior stage + old breadth read; NEW = the FIXED
     replay's prior stage + fixed breadth read (+ birth-filled prior breadth). OLD vs stored stage is
     the replay's FIDELITY. A row changes only where NEW != OLD (the rule inputs differ), and then
     takes NEW; elsewhere the stored stage stands — so a mis-modelled row never manufactures a change.
     Cascade = a changed prior stage propagating (e.g. Fading held through an RS hold branch).
  2. Every mi_ep_alerts row since 2026-08-01: rebuild the theme board the scan saw (latest row per name
     written before the alert, within 7 days, latest not Retired), under stored and under fixed stages.
     Who had the +10: mi_ep_scan_log.score_breakdown (from 08-29, exact) > belonging shadow (from 09-13)
     > mi_ep_alerts.in_active_theme. An alert LOSES the +10 when every paying-stage theme (Accelerating/
     Mainstream) that carried it — listed, or the belonging fit theme — is not paying under the fix.
  3. Score after: presented = T(round(max(raw, floor) x regime_mult, 1)); T(x) = round(1.25x + 15, 1) on
     the separation table, identity on legacy; raw loses the 10-point theme_bonus; the floor (the
     conviction floor rules) still applies. Exact where a breakdown exists (the multiplier is the one
     that REPRODUCES the stored score — checked per alert); otherwise approx (score - 10 x mult x slope).

NOT MODELLED (stated, not hidden): a forced-Fading prior triggers a news refresh the next night whose
score cannot be replayed (the stored score is used); validation/merge/rename side effects of a stage
change; a /promotetheme row later overwritten by the engine (the board uses the stored stage).
"""
from __future__ import annotations

import json
import sys
from bisect import bisect_right
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

# ── the engine's constants (theme_engine.py / ep_rubric.py — cross-checked at runtime when importable)
BREADTH_DECAY_THRESHOLD = 0.40
PAYING = ("Accelerating", "Mainstream")          # ep_theme_belonging.THEME_BONUS_STAGES
THEME_BONUS_POINTS = 10.0
BAR_65 = 65.0
SEPARATION_SCALE = (1.25, 15.0)                   # SCORE_WEIGHTS["output_scale"] mult/offset
FLOOR_RULES = {
    "separation": [(10, "game_changer", 60)],
    "legacy": [(15, "game_changer", 80), (20, "strong", 80), (15, "strong", 70),
               (10, "game_changer", 60)],
}
SEPARATION_LIVE_FROM = date(2026, 8, 22)         # #533 separation + rescale shipped
REGIME_MULTS = (1.0, 1.2)                         # ep_detector: 1.2 if Bull else 1.0

REPLAY_FROM = date(2026, 7, 24)
HISTORY_FROM = REPLAY_FROM - timedelta(days=8)
ALERTS_FROM = date(2026, 8, 1)
NIGHTLY_PROMOTE_AFTER_ET = time(16, 30)           # promote job 17:05 ET; earlier = an intraday /promotetheme


# ═══════════════════════════════════ PURE PARTS (unit-tested) ═══════════════════════════════════

def breadth_above_sma20(rows) -> float | None:
    """db.breadth_above_sma20, verbatim arithmetic: close > sma_20 among rows carrying both."""
    above = total = 0
    for r in rows:
        close, sma = r.get("close"), r.get("sma_20")
        if close is None or sma is None:
            continue
        total += 1
        if close > sma:
            above += 1
    return None if not total else round(above / total, 3)


def prior_counts(prev_breadth, *, fixed: bool) -> bool:
    """Does last night's stored breadth count as a night below the bar?"""
    if fixed:
        return prev_breadth is not None and prev_breadth < BREADTH_DECAY_THRESHOLD
    return (prev_breadth or 1.0) < BREADTH_DECAY_THRESHOLD


def stage_rule(total_score: float, hist_scores_desc: list[float], prev_score: float, prev_stage: str,
               breadth, prev_breadth, desc_ok: bool, *, fixed: bool) -> str:
    """theme_engine._rescore_existing_theme's stage block (main branch), line for line.
    `hist_scores_desc`: the 7-day history's scores, NEWEST FIRST (as `_get_theme_history` returns)."""
    hs = hist_scores_desc[-3:]                       # the engine reads history[-3:] of a DESC list
    smoothed_prev = sum(hs) / len(hs) if hs else prev_score
    smooth_delta = total_score - smoothed_prev
    age_days = len(hist_scores_desc)
    if smooth_delta > 8:
        stage = "Accelerating"
    elif smooth_delta < -8:
        stage = "Fading"
    elif age_days >= 5 and total_score >= 50:
        stage = "Mainstream"
    else:
        stage = prev_stage
        if stage == "Fading" and smooth_delta > 5:
            stage = "Accelerating"
    if stage != prev_stage and stage in ("Accelerating", "Fading") and age_days >= 1:
        y_delta = (hist_scores_desc[0] or 0) - smoothed_prev
        confirmed = ((stage == "Accelerating" and y_delta > 5)
                     or (stage == "Fading" and y_delta < -8))
        if not confirmed:
            stage = prev_stage
    if (breadth is not None and breadth < BREADTH_DECAY_THRESHOLD
            and prior_counts(prev_breadth, fixed=fixed) and stage != "Fading"):
        stage = "Fading"
    if not desc_ok and stage in ("Accelerating", "Mainstream"):
        stage = "Nascent"
    return stage


def pick_latest_complete(counts_desc: list[tuple[date, int]]) -> date | None:
    """db._pick_latest_complete_score_date: newest date whose row count >= 50% of the median of
    the 10 newest counts. `counts_desc`: (score_date, n) newest first."""
    if not counts_desc:
        return None
    recent = sorted(n for _, n in counts_desc[:10])
    mid = len(recent) // 2
    median = recent[mid] if len(recent) % 2 else (recent[mid - 1] + recent[mid]) / 2
    for d, n in counts_desc:
        if n >= 0.5 * median:
            return d
    return None


def present(raw: float, mult: float, side: str) -> float:
    """_score_ep's last two steps: round(raw x regime mult, 1), then the side's output scale."""
    final = round(raw * mult, 1)
    if side == "separation":
        a, b = SEPARATION_SCALE
        return round(a * final + b, 1)
    return final


def resolve_floor(gap_pct, catalyst, side: str):
    if gap_pct is None:
        return None
    for min_gap, cat, floor in FLOOR_RULES[side]:
        if gap_pct >= min_gap and catalyst == cat:
            return floor
    return None


def score_without_bonus(breakdown: dict, stored_score: float, side: str, gap_pct, catalyst,
                        fallback_mult: float) -> dict:
    """Exact before/after from a stored score_breakdown (raw components; `conviction_floor` holds the
    bump the floor added, 0 when a rule matched but did not bind, absent when no rule matched)."""
    comps = {}
    for k, v in (breakdown or {}).items():
        if k == "conviction_floor":
            continue
        try:
            comps[k] = float(v)
        except (TypeError, ValueError):
            continue
    s = sum(comps.values())
    bonus = comps.get("theme_bonus", 0.0)
    bump = breakdown.get("conviction_floor") if breakdown else None
    if bump is not None and float(bump) > 0:
        floor = s + float(bump)
    elif breakdown and "conviction_floor" in breakdown:
        floor = resolve_floor(gap_pct, catalyst, side)
    else:
        floor = None
    raw_b = max(s, floor) if floor is not None else s
    raw_a = max(s - bonus, floor) if floor is not None else s - bonus
    mult, reproduced = None, False
    for m in REGIME_MULTS:
        if stored_score is not None and abs(present(raw_b, m, side) - stored_score) <= 0.051:
            mult, reproduced = m, True
            break
    if mult is None:
        mult = fallback_mult
    return {"before": present(raw_b, mult, side), "after": present(raw_a, mult, side),
            "bonus_points": bonus, "floor": floor, "mult": mult, "reproduced": reproduced}


def approx_delta(mult: float, side: str) -> float:
    """Presented value of the 10 raw points when no breakdown exists (floor not modelled)."""
    return round(THEME_BONUS_POINTS * mult * (SEPARATION_SCALE[0] if side == "separation" else 1.0), 2)


def crosses(before, after, bar) -> bool:
    if before is None or after is None or bar is None:
        return False
    return (before >= bar) != (after >= bar)


# ═══════════════════════════════════ SELF-TEST (no DB) ═══════════════════════════════════════════

def selftest() -> int:
    fails = []

    def check(label, got, want):
        ok = got == want
        print(f"  {'ok ' if ok else 'FAIL'} {label}: got {got!r} want {want!r}")
        if not ok:
            fails.append(label)

    print("breadth arithmetic")
    check("empty -> None", breadth_above_sma20([]), None)
    check("all below -> 0.0 (not None)",
          breadth_above_sma20([{"close": 9, "sma_20": 10}, {"close": 8, "sma_20": 10}]), 0.0)
    check("equal is not above", breadth_above_sma20([{"close": 10, "sma_20": 10}]), 0.0)
    check("2 of 3", breadth_above_sma20([{"close": 11, "sma_20": 10}, {"close": 9, "sma_20": 10},
                                         {"close": 12, "sma_20": 10}]), 0.667)
    print("prior-night read")
    for prev, old, new in [(0.0, False, True), (None, False, False), (0.2, True, True),
                           (0.4, False, False), (0.9, False, False)]:
        check(f"prev={prev} old", prior_counts(prev, fixed=False), old)
        check(f"prev={prev} fixed", prior_counts(prev, fixed=True), new)
    print("stage rule (5 rows of history at 74, score 74.5: the RS rule alone says Mainstream)")
    h = [74.0] * 5
    check("prev 0.0, tonight 0.0: old keeps Mainstream",
          stage_rule(74.5, h, 74, "Mainstream", 0.0, 0.0, True, fixed=False), "Mainstream")
    check("prev 0.0, tonight 0.0: fixed fades",
          stage_rule(74.5, h, 74, "Mainstream", 0.0, 0.0, True, fixed=True), "Fading")
    check("prev None: fixed keeps Mainstream",
          stage_rule(74.5, h, 74, "Mainstream", 0.0, None, True, fixed=True), "Mainstream")
    check("prev 0.2: both fade (unchanged case)",
          (stage_rule(74.5, h, 74, "Mainstream", 0.2, 0.2, True, fixed=False),
           stage_rule(74.5, h, 74, "Mainstream", 0.2, 0.2, True, fixed=True)), ("Fading", "Fading"))
    check("breadth back to 0.5 after a forced fade: Mainstream again (age>=5, score>=50)",
          stage_rule(74.5, h, 74, "Fading", 0.5, 0.0, True, fixed=True), "Mainstream")
    check("cascade: young theme (age 3) held in the RS hold branch stays Fading",
          stage_rule(45.0, [44.0] * 3, 44, "Fading", 0.5, 0.0, True, fixed=True), "Fading")
    check("same young theme with an Accelerating prior holds Accelerating",
          stage_rule(45.0, [44.0] * 3, 44, "Accelerating", 0.5, 0.0, True, fixed=True), "Accelerating")
    check("description cap still caps a non-Fading stage",
          stage_rule(74.5, h, 74, "Mainstream", 0.5, 0.0, False, fixed=True), "Nascent")
    print("completeness (a 1-row stray day is skipped)")
    check("stray today skipped",
          pick_latest_complete([(date(2026, 9, 30), 1)] + [(date(2026, 9, 29) - timedelta(days=i), 2400)
                                                           for i in range(10)]), date(2026, 9, 29))
    print("score transform (separation: T(x) = 1.25x + 15)")
    bd = {"gap": 20, "liquidity": 10, "catalyst": 10, "float": 0, "vol_conviction": 0, "theme_bonus": 10}
    r = score_without_bonus(bd, 90.0, "separation", 12.0, "strong", 1.0)
    check("raw 50, Bull: 90 -> 75", (r["before"], r["after"], r["mult"], r["reproduced"]),
          (90.0, 75.0, 1.2, True))
    r = score_without_bonus(bd, 77.5, "separation", 12.0, "strong", 1.2)
    check("raw 50, Neutral: 77.5 -> 65.0 (lands ON the bar)", (r["before"], r["after"], r["mult"]),
          (77.5, 65.0, 1.0))
    check("77.5 -> 65.0 does not cross 65", crosses(77.5, 65.0, BAR_65), False)
    r = score_without_bonus(dict(bd, catalyst=5), 71.2, "separation", 12.0, "strong", 1.0)
    check("raw 45, Neutral: 71.2 -> 58.8 crosses 65",
          (r["before"], r["after"], crosses(r["before"], r["after"], BAR_65)), (71.2, 58.8, True))
    fb = {"gap": 10, "liquidity": 10, "catalyst": 15, "float": 0, "vol_conviction": 0,
          "theme_bonus": 10, "conviction_floor": 15}
    r = score_without_bonus(fb, 90.0, "separation", 11.0, "game_changer", 1.0)
    check("floor 60 binds: score unchanged without the bonus", (r["before"], r["after"], r["floor"]),
          (90.0, 90.0, 60.0))
    fz = {"gap": 20, "liquidity": 10, "catalyst": 15, "float": 5, "vol_conviction": 5,
          "theme_bonus": 10, "conviction_floor": 0}
    r = score_without_bonus(fz, 96.2, "separation", 11.0, "game_changer", 1.0)
    check("floor rule matched but not binding (raw 65 -> 96.2): after = max(55, 60) = 60 raw -> 90.0",
          (r["before"], r["after"], r["reproduced"]), (96.2, 90.0, True))
    check("legacy side is the raw scale", present(50, 1.2, "legacy"), 60.0)
    check("approx presented delta, separation Bull", approx_delta(1.2, "separation"), 15.0)
    print(f"\nselftest: {'PASS' if not fails else 'FAIL'} ({len(fails)} failed)")
    return 1 if fails else 0


# ═══════════════════════════════════ THE REPLAY (read-only DB) ════════════════════════════════════

def _d(x) -> date:
    return x if isinstance(x, date) and not isinstance(x, datetime) else date.fromisoformat(str(x)[:10])


def _et(ts):
    if ts is None:
        return None
    return ts.astimezone(ET) if ts.tzinfo else ts.replace(tzinfo=ZoneInfo("UTC")).astimezone(ET)


def _jsonb(v):
    if v is None or isinstance(v, dict):
        return v
    try:
        return json.loads(v)
    except (TypeError, ValueError):
        return None


def log(msg=""):
    print(msg, file=sys.stderr)


def emit(obj):
    print(json.dumps(obj, default=str, sort_keys=True))


async def main() -> int:
    from agents.market_intelligence.db import get_pool
    try:
        from agents.market_intelligence.theme_engine import (
            _BREADTH_DECAY_THRESHOLD, _check_description_quality)
        assert _BREADTH_DECAY_THRESHOLD == BREADTH_DECAY_THRESHOLD, "threshold drifted"
        desc_check = _check_description_quality
    except ImportError as e:
        log(f"WARN description-quality check not importable ({e}) — treated as passing")
        desc_check = None
    try:
        from agents.market_intelligence import ep_rubric as R
        assert (R.SCORE_WEIGHTS["output_scale"]["mult"], R.SCORE_WEIGHTS["output_scale"]["offset"]) \
            == SEPARATION_SCALE, "output scale drifted"
        assert R.SCORE_WEIGHTS["theme_bonus"]["points"] == THEME_BONUS_POINTS, "theme bonus drifted"
        assert [(r["min_gap"], r["catalyst"], r["floor"]) for r in R.SCORE_WEIGHTS["conviction_floor"]["rules"]] \
            == FLOOR_RULES["separation"], "separation floor drifted"
        assert [(r["min_gap"], r["catalyst"], r["floor"]) for r in R.SCORE_WEIGHTS_LEGACY["conviction_floor"]["rules"]] \
            == FLOOR_RULES["legacy"], "legacy floor drifted"
        log("constants cross-checked against the running ep_rubric/theme_engine: OK")
    except ImportError as e:
        log(f"WARN ep_rubric not importable ({e}) — using the probe's constants")

    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction(readonly=True):
            themes = [dict(r) for r in await conn.fetch("""
                SELECT theme_date, name, stage, score, rs_avg, pct_above_20sma, tickers, source,
                       created_at, description
                FROM mi_themes WHERE theme_date >= $1 ORDER BY name, theme_date""", HISTORY_FROM)]
            counts = [(r["score_date"], r["n"]) for r in await conn.fetch("""
                SELECT score_date, COUNT(*) AS n FROM mi_stock_scores
                WHERE score_date >= $1 GROUP BY score_date ORDER BY score_date DESC""",
                HISTORY_FROM - timedelta(days=40))]
            birth_tk = sorted({tk for t in themes if t["stage"] != "Retired"
                               and t["pct_above_20sma"] is None for tk in (t["tickers"] or [])})
            score_rows = await conn.fetch("""
                SELECT ticker, score_date, close, sma_20 FROM mi_stock_scores
                WHERE score_date >= $1 AND ticker = ANY($2)""", HISTORY_FROM - timedelta(days=10), birth_tk)
            alerts = [dict(r) for r in await conn.fetch("""
                SELECT id, ticker, alert_date, detected_at, created_at, ep_score, score_tier,
                       in_active_theme, source, gap_pct, catalyst_quality
                FROM mi_ep_alerts WHERE alert_date >= $1 ORDER BY alert_date, id""", ALERTS_FROM)]
            a_tk = sorted({a["ticker"] for a in alerts})
            scanlog = [dict(r) for r in await conn.fetch("""
                SELECT scan_date, ticker, ep_score, score_breakdown, ep_bar, score_side, scan_time_et,
                       catalyst_quality, gap_pct
                FROM mi_ep_scan_log
                WHERE scan_date >= $1 AND ticker = ANY($2) AND score_breakdown IS NOT NULL""",
                ALERTS_FROM, a_tk)]
            shadow = [dict(r) for r in await conn.fetch("""
                SELECT scan_date, ticker, listed, fit_status, fit_theme, fit_stage, acting_in_theme,
                       belongs_paying, toggle_on, ep_score_listed_only_last,
                       ep_score_with_belonging_last, ep_bar
                FROM mi_ep_theme_belonging_shadow WHERE scan_date >= $1""", ALERTS_FROM)]
            regimes = [dict(r) for r in await conn.fetch("""
                SELECT regime_date, regime, ep_threshold FROM mi_market_regime
                WHERE regime_date >= $1 ORDER BY regime_date""", ALERTS_FROM - timedelta(days=10))]

    # ── 1. birth fill ─────────────────────────────────────────────────────────────────────────
    scores_by_date: dict[date, dict[str, dict]] = defaultdict(dict)
    for r in score_rows:
        scores_by_date[_d(r["score_date"])][r["ticker"]] = {"close": r["close"], "sma_20": r["sma_20"]}
    counts_desc = sorted(((_d(d), n) for d, n in counts), reverse=True)

    def complete_on_or_before(bound: date):
        return pick_latest_complete([(d, n) for d, n in counts_desc if d <= bound])

    def fill(t) -> tuple[float | None, date | None]:
        d = _d(t["theme_date"])
        if t.get("source") == "shadow_promoted":
            made = _et(t.get("created_at"))
            intraday = made is not None and made.date() == d and made.time() < NIGHTLY_PROMOTE_AFTER_ET
            sd = complete_on_or_before(d - timedelta(days=1) if intraday else d)
        else:
            sd = d                                       # engine birth: the run's own date
        if sd is None:
            return None, None
        rows = [scores_by_date[sd][tk] for tk in set(t["tickers"] or []) if tk in scores_by_date[sd]]
        return breadth_above_sma20(rows), sd

    # ── 2. stage replay ───────────────────────────────────────────────────────────────────────
    by_name: dict[str, list[dict]] = defaultdict(list)
    for t in themes:
        t["theme_date"] = _d(t["theme_date"])
        by_name[t["name"]].append(t)
    kinds = Counter()
    fidelity = Counter()
    fid_by_stage = defaultdict(Counter)
    old_cond_rows = old_cond_fading = 0
    changed_rows = []
    for name, rows in by_name.items():
        rows.sort(key=lambda t: t["theme_date"])
        for i, r in enumerate(rows):
            d = r["theme_date"]
            r["fixed_stage"], r["fixed_breadth"], r["kind"] = r["stage"], r["pct_above_20sma"], None
            hist = [p for p in rows[:i] if d - timedelta(days=7) <= p["theme_date"] < d][::-1]
            p = hist[0] if hist else None
            if r["stage"] == "Retired":
                r["kind"] = "retired"
            elif p is None or p["stage"] == "Retired" or r["pct_above_20sma"] is None:
                r["kind"] = "birth"
                if r["pct_above_20sma"] is None:
                    r["fixed_breadth"], r["fill_date"] = fill(r)
            elif r["stage"] == "Fading" and r["rs_avg"] is None:
                r["kind"] = "fading_branch"              # lacks strong stocks: Fading before the rule
            else:
                r["kind"] = "rescore"
            if d < REPLAY_FROM:
                continue
            kinds[r["kind"]] += 1
            if r["kind"] != "rescore":
                continue
            hs = [float(h["score"] or 0) for h in hist]
            desc_ok = True if desc_check is None else desc_check(name, list(r["tickers"] or []),
                                                                  r["description"])[0]
            score = float(r["score"] or 0)
            old = stage_rule(score, hs, float(p["score"] or 0), p["stage"], r["pct_above_20sma"],
                             p["pct_above_20sma"], desc_ok, fixed=False)
            new = stage_rule(score, hs, float(p["score"] or 0), p["fixed_stage"], r["pct_above_20sma"],
                             p["fixed_breadth"], desc_ok, fixed=True)
            agree = old == r["stage"]
            fidelity[agree] += 1
            fid_by_stage[r["stage"]][agree] += 1
            pb = p["pct_above_20sma"]
            if (r["pct_above_20sma"] is not None and r["pct_above_20sma"] < BREADTH_DECAY_THRESHOLD
                    and pb is not None and 0 < pb < BREADTH_DECAY_THRESHOLD):
                old_cond_rows += 1
                old_cond_fading += r["stage"] == "Fading"
            if new != old:
                if p["fixed_stage"] != p["stage"]:
                    cause = "cascade"
                elif pb == 0.0:
                    cause = "zero_prior"
                elif pb is None and p["fixed_breadth"] is not None:
                    cause = "birth_fill"
                else:
                    cause = "other"
                r["fixed_stage"] = new
                changed_rows.append(r)
                r["cause"] = cause
                r["recompute_agrees"] = agree
                r["prev"] = p
    for r in changed_rows:
        p = r["prev"]
        emit({"kind": "theme_day", "theme_date": r["theme_date"], "name": r["name"],
              "stored_stage": r["stage"], "fixed_stage": r["fixed_stage"], "cause": r["cause"],
              "breadth": r["pct_above_20sma"], "prev_date": p["theme_date"],
              "prev_breadth_stored": p["pct_above_20sma"], "prev_breadth_fixed": p["fixed_breadth"],
              "prev_stage_stored": p["stage"], "prev_stage_fixed": p["fixed_stage"],
              "score": r["score"], "members": len(r["tickers"] or []),
              "recompute_agrees_with_stored": r["recompute_agrees"]})

    # ── 3. EP alerts ─────────────────────────────────────────────────────────────────────────
    idx = {name: ([t["theme_date"] for t in rows], rows) for name, rows in by_name.items()}

    def board(d: date, ts):
        """{name: row} the scan saw: latest row before the alert, within 7 days, latest not Retired."""
        out = {}
        for name, (dates, rows) in idx.items():
            j = bisect_right(dates, d) - 1
            while j >= 0:
                t = rows[j]
                if t["theme_date"] < d:
                    break
                c = t.get("created_at")
                if ts is not None and c is not None and c <= ts:
                    break                                    # written today before the alert
                j -= 1
            if j < 0:
                continue
            t = rows[j]
            if t["theme_date"] < d - timedelta(days=7) or t["stage"] == "Retired":
                continue
            out[name] = t
        return out

    sl_by = defaultdict(list)
    for s in scanlog:
        sl_by[(_d(s["scan_date"]), s["ticker"])].append(s)
    sh_by = {(_d(s["scan_date"]), s["ticker"]): s for s in shadow}
    reg_dates = [_d(r["regime_date"]) for r in regimes]

    def regime_before(d: date):
        j = bisect_right(reg_dates, d - timedelta(days=1)) - 1
        return regimes[j] if j >= 0 else None

    tallies = Counter()
    listed_agree = Counter()
    for a in alerts:
        d = _d(a["alert_date"])
        ts = a.get("detected_at") or a.get("created_at")
        b = board(d, ts)
        paying_stored = sorted(n for n, t in b.items()
                               if t["stage"] in PAYING and a["ticker"] in (t["tickers"] or []))
        paying_fixed = sorted(n for n, t in b.items()
                              if t["fixed_stage"] in PAYING and a["ticker"] in (t["tickers"] or []))
        if a.get("in_active_theme") is not None:
            listed_agree[bool(paying_stored) == bool(a["in_active_theme"])] += 1
        sh = sh_by.get((d, a["ticker"]))
        fit_theme = sh["fit_theme"] if sh and sh.get("fit_status") == "confirmed" else None
        fit_row = b.get(fit_theme) if fit_theme else None
        src_stored = set(paying_stored) | ({fit_theme} if fit_row and fit_row["stage"] in PAYING else set())
        src_fixed = set(paying_fixed) | ({fit_theme} if fit_row and fit_row["fixed_stage"] in PAYING else set())
        # who had the +10
        cands = sl_by.get((d, a["ticker"]), [])
        sl = None
        if cands:
            exact = [s for s in cands if s["ep_score"] is not None and a["ep_score"] is not None
                     and abs(s["ep_score"] - a["ep_score"]) <= 0.051]
            pool_ = exact or cands
            sl = max(pool_, key=lambda s: (s["scan_time_et"] is not None, s["scan_time_et"] or 0))
            sl_match = "exact" if exact else "nearest"
        bd = _jsonb(sl["score_breakdown"]) if sl else None
        if bd is not None:
            had = float(bd.get("theme_bonus") or 0) > 0
            had_src = "scan_log"
        elif sh is not None and sh.get("acting_in_theme") is not None:
            had, had_src = bool(sh["acting_in_theme"]), "belonging_shadow"
        else:
            had, had_src = bool(a.get("in_active_theme")), "in_active_theme"
        tallies[f"had_bonus={had}"] += 1
        if had and not src_stored:
            tallies["had_bonus_but_no_paying_theme_found (fidelity miss)"] += 1
            continue
        loses = had and not src_fixed
        gains = (not had) and bool(src_fixed) and not src_stored
        if not (loses or gains):
            if had and set(src_stored) != set(src_fixed):
                tallies["keeps_bonus_via_another_theme"] += 1
            continue
        reg = regime_before(d)
        fallback_mult = 1.2 if reg and reg["regime"] == "Bull" else 1.0
        if bd is not None:
            side = sl.get("score_side") or ("separation" if d >= SEPARATION_LIVE_FROM else "legacy")
            if loses:
                s = score_without_bonus(bd, a["ep_score"], side, sl.get("gap_pct") or a.get("gap_pct"),
                                        sl.get("catalyst_quality") or a.get("catalyst_quality"),
                                        fallback_mult)
                before, after = a["ep_score"], s["after"]
                method = "exact" if s["reproduced"] and sl_match == "exact" else "exact_unverified"
                mult = s["mult"]
            else:
                before = a["ep_score"]
                after = round(before + approx_delta(fallback_mult, side), 1)
                method, mult = "approx_gain", fallback_mult
            acting_bar = sl.get("ep_bar")
        else:
            side = "separation" if d >= SEPARATION_LIVE_FROM else "legacy"
            delta = approx_delta(fallback_mult, side)
            before = a["ep_score"]
            after = round(before - delta if loses else before + delta, 1)
            method, mult = "approx_no_breakdown", fallback_mult
            acting_bar = (sh or {}).get("ep_bar") or (reg or {}).get("ep_threshold")
        tallies["LOSES" if loses else "GAINS"] += 1
        c65 = crosses(before, after, BAR_65)
        cbar = crosses(before, after, acting_bar)
        tallies[f"{'LOSES' if loses else 'GAINS'}_crosses_65"] += c65
        tallies[f"{'LOSES' if loses else 'GAINS'}_crosses_acting_bar"] += cbar
        emit({"kind": "alert", "id": a["id"], "ticker": a["ticker"], "alert_date": d,
              "source": a.get("source"), "score_tier": a.get("score_tier"),
              "change": "loses_bonus" if loses else "gains_bonus",
              "score_before": before, "score_after": after, "method": method,
              "score_side": side, "regime_mult": mult,
              "crosses_65": c65, "above_65_before": before is not None and before >= BAR_65,
              "acting_bar": acting_bar, "crosses_acting_bar": cbar,
              "bonus_evidence": had_src, "paying_themes_stored": sorted(src_stored),
              "paying_themes_fixed": sorted(src_fixed),
              "lost_themes": sorted(src_stored - src_fixed)})

    # independent check: the bonus's presented value where the shadow scored both ways
    diffs = Counter()
    for s in shadow:
        x, y = s.get("ep_score_listed_only_last"), s.get("ep_score_with_belonging_last")
        if x is None or y is None or s.get("listed") == s.get("belongs_paying"):
            continue
        dd = round(abs(x - y), 1)
        diffs["12.5 (Neutral)" if abs(dd - 12.5) <= 0.15 else "15.0 (Bull)" if abs(dd - 15) <= 0.15
              else "other (floor bound / legacy)"] += 1

    # ── summary ──────────────────────────────────────────────────────────────────────────────
    since = [r for r in changed_rows if r["theme_date"] >= ALERTS_FROM]
    log(f"\n=== #580 breadth-fix replay — mi_themes {REPLAY_FROM}..{max(t['theme_date'] for t in themes)}, "
        f"EP alerts since {ALERTS_FROM} ===")
    log(f"theme rows replayed by kind: {dict(kinds)}")
    log(f"FIDELITY — old-rule recompute == stored stage on rescore rows: {fidelity[True]} of "
        f"{sum(fidelity.values())} ({100 * fidelity[True] / max(1, sum(fidelity.values())):.1f}%)")
    for st, c in sorted(fid_by_stage.items()):
        log(f"   stored {st:<12}: {c[True]} of {sum(c.values())} agree")
    log(f"FIDELITY — the old rule's own condition (0 < prior < 0.40, tonight < 0.40) -> stored Fading: "
        f"{old_cond_fading} of {old_cond_rows}")
    births_null = [t for rows in by_name.values() for t in rows
                   if t["theme_date"] >= REPLAY_FROM and t["kind"] == "birth" and t["pct_above_20sma"] is None]
    log(f"birth fill: {len(births_null)} NULL birth rows -> filled {sum(t['fixed_breadth'] is not None for t in births_null)}"
        f" (of which 0.0: {sum(t['fixed_breadth'] == 0.0 for t in births_null)}; "
        f"below 0.40: {sum(t['fixed_breadth'] is not None and t['fixed_breadth'] < 0.4 for t in births_null)})")
    log(f"CHANGED theme-days: {len(changed_rows)} total, {len(since)} since {ALERTS_FROM} | by cause "
        f"{dict(Counter(r['cause'] for r in changed_rows))} | stored->fixed "
        f"{dict(Counter((r['stage'], r['fixed_stage']) for r in changed_rows))}")
    log(f"   paying stage (Accelerating/Mainstream) -> not paying: "
        f"{sum(r['stage'] in PAYING and r['fixed_stage'] not in PAYING for r in changed_rows)} theme-days, "
        f"{len({r['name'] for r in changed_rows if r['stage'] in PAYING and r['fixed_stage'] not in PAYING})} themes")
    log(f"FIDELITY — computed 'listed at scan time' == mi_ep_alerts.in_active_theme: "
        f"{listed_agree[True]} of {sum(listed_agree.values())}")
    log(f"EP alerts since {ALERTS_FROM}: {len(alerts)} | {dict(tallies)}")
    log(f"CHECK — shadow listed-vs-belonging score gaps (the bonus's presented value): {dict(diffs)}")
    log("stdout: one JSON line per changed theme-day and per changed alert.")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv[1:]:
        sys.exit(selftest())
    import asyncio
    sys.exit(asyncio.run(main()))
