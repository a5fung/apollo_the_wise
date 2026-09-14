#!/usr/bin/env python3
"""Theme BELONGING backtest — stage 2 of 2: the replay of the TWO-STAGE rule (2026-09-14).

    bash   scripts/probes/_ep_theme_belonging_pull.sh <dir>            # read-only prod pull
    python scripts/probes/_ep_theme_belonging_backtest.py <dir>        # stage 1 + the PRICE
    python scripts/probes/_ep_theme_belonging_backtest.py <dir> --spend   # stage 2 (paid, cached)

Replays every EP alert in `alerts.csv` under the rule that ships in ep_theme_belonging.py —
the SAME functions the live scan runs (session_index / log_returns / excess_returns /
build_baskets / score_belonging for stage 1; theme_engine.judge_theme_fit for stage 2), every
input strictly before the alert date:
  * board as-of each alert = the latest mi_themes row per name written in the 7 days BEFORE the
    alert date, Retired dropped (the mirror of get_active_themes(stale_after_days=7) at a
    morning scan — 94% of theme rows are written 17:00-17:59 ET the night before);
  * stage 1 = listed, or a correlation SHORTLIST (BELONGING_SHORTLIST_CORR_BAR, top
    BELONGING_SHORTLIST_THEMES) of paying-stage baskets, plus the Nascent shortlist;
  * stage 2 = the nightly assignment judgement on the shortlist (description = the nightly's
    own one-liner from mi_ticker_overrides / the static universe, else the yfinance profile
    paragraph capped at 300 chars — the live path's own fallback). Verdicts are cached to
    <dir>/fit_verdicts.json on run ONE and never re-bought (COST EFFICIENCY rule).
  * the Nascent question, SEPARATELY: names not belonging at the paying stages get a second
    judgement against their Nascent shortlist — reported as its own number, never bundled.

SCORE EFFECT without re-scoring components (only 10 of 346 alerts carry the full component
vector): every component is an INTEGER, so raw = final / multiplier must be near-integral —
the multiplier (regime 1.2 if Bull x confidence) is checked that way, the era bar is the row's
own (`ep_bar` since #605, else 65 presented on the separation side since 2026-08-22, else the
regime's raw threshold), and the +10's effect is max(raw+10, floor) x mult (presented through
apply_output_scale on the separation side). The one ambiguity — a conviction floor that BOUND
(raw < floor) — is resolved from the stored breakdown where one exists and otherwise reported as
"possible", never silently resolved either way.

Writes <dir>/results.md, <dir>/per_alert.csv, <dir>/fit_verdicts.json.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import sys
import time
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agents.market_intelligence import ep_theme_belonging as etb  # noqa: E402
from agents.market_intelligence.ep_rubric import (  # noqa: E402
    SCORE_WEIGHTS, SCORE_WEIGHTS_LEGACY, SEPARATION_BAR, apply_output_scale, resolve_conviction_floor)

SEPARATION_LIVE_FROM = date(2026, 8, 22)
NAMED_WRONG = {("2026-05-18", "D"), ("2026-05-19", "BKKT"), ("2026-05-21", "QBTS"), ("2026-05-18", "CMPS")}
NAMED_RIGHT = {("2026-07-20", "IREN")}
NAMED_HIGHS = {("2026-09-03", "SNOW"), ("2026-09-03", "HOOD"), ("2026-07-31", "BLZE"), ("2026-06-17", "AEHR")}
EST_IN_TOK, EST_OUT_TOK = 1200, 250


# ── loading ─────────────────────────────────────────────────────────────────────────────────
def _f(x):
    try:
        return float(x) if x not in (None, "") else None
    except ValueError:
        return None


def _b(x):
    return {"t": True, "true": True, "f": False, "false": False}.get(str(x).lower())


def _pg_array(text: str) -> list[str]:
    s = (text or "").strip()
    if not s.startswith("{"):
        return []
    s = s[1:-1]
    out, cur, q = [], "", False
    for ch in s:
        if ch == '"':
            q = not q
        elif ch == "," and not q:
            out.append(cur); cur = ""
        else:
            cur += ch
    if cur:
        out.append(cur)
    return [t.strip().upper() for t in out if t.strip()]


def load(d: Path):
    alerts = list(csv.DictReader((d / "alerts.csv").open()))
    themes = list(csv.DictReader((d / "themes.csv").open()))
    for t in themes:
        t["tickers"] = _pg_array(t["tickers"])
        t["theme_date"] = date.fromisoformat(t["theme_date"])
    desc = {r["ticker"].upper(): r for r in csv.DictReader((d / "descriptions.csv").open())}
    closes: dict[str, dict[date, float]] = defaultdict(dict)
    with (d / "closes.csv").open() as fh:
        for r in csv.DictReader(fh):
            closes[r["ticker"].upper()][date.fromisoformat(r["trade_date"])] = float(r["close"])
    return alerts, themes, desc, closes


def board_as_of(themes: list[dict], d: date) -> list[dict]:
    latest: dict[str, dict] = {}
    for t in themes:
        if d - timedelta(days=7) <= t["theme_date"] < d:
            cur = latest.get(t["name"])
            if cur is None or t["theme_date"] > cur["theme_date"]:
                latest[t["name"]] = t
    return [t for t in latest.values() if (t.get("stage") or "").strip() != "Retired"]


# ── stage 1 ─────────────────────────────────────────────────────────────────────────────────
class DayContext:
    def __init__(self, d: date, board: list[dict], closes):
        self.d, self.board = d, board
        self.cs = etb.session_index(closes.get("SPY", {}), d)
        self.market = etb.log_returns(closes.get("SPY", {}), self.cs)
        members = set()
        for t in board:
            if (t.get("stage") or "").strip() in etb.BELONGING_SHADOW_STAGES:
                members.update(t["tickers"])
        self.excess = etb.excess_returns({m: closes.get(m, {}) for m in members}, self.cs, self.market) \
            if len(self.cs) > 1 else {}
        self.baskets = etb.build_baskets(board, self.excess)
        self.listed = etb.listed_paying_set(board)
        self.themes_by_name = {t["name"]: t for t in board
                               if (t.get("stage") or "").strip() in etb.BELONGING_SHADOW_STAGES}
        self._closes = closes

    def vec(self, ticker: str):
        if ticker in self.excess:
            return self.excess[ticker]
        if len(self.cs) < 2:
            return None
        r = etb.log_returns(self._closes.get(ticker, {}), self.cs)
        if r.shape != self.market.shape:
            return None
        v = r - self.market
        return v if etb._usable(v, etb.BELONGING_MIN_OVERLAP_SESSIONS) else None

    @property
    def n_paying(self):
        return sum(1 for b in self.baskets if b.stage in etb.THEME_BONUS_STAGES)

    @property
    def n_nascent(self):
        return sum(1 for b in self.baskets if b.stage == "Nascent")


# ── the score arithmetic ────────────────────────────────────────────────────────────────────
def score_effect(row: dict) -> dict:
    """before / bar / lift for the +10, from the stored final score. See module docstring."""
    d = date.fromisoformat(row["alert_date"])
    score = _f(row["ep_score"])
    sep = d >= SEPARATION_LIVE_FROM
    weights = SCORE_WEIGHTS if sep else SCORE_WEIGHTS_LEGACY
    bar = _f(row.get("ep_bar")) or (float(SEPARATION_BAR) if sep else (_f(row.get("regime_ep_threshold")) or 70.0))
    regime_mult = 1.2 if (row.get("regime") or "") == "Bull" else 1.0
    conf = _f(row.get("confidence_multiplier")) or 1.0
    scale = weights.get("output_scale")
    unscaled = (score - scale["offset"]) / scale["mult"] if scale else score
    # the multiplier: the regime-implied one first, alternatives only if it does not reproduce
    chosen, raw = None, None
    for mult in ([regime_mult * conf] + [m for m in (1.0, 1.2, 1.44) if abs(m - regime_mult * conf) > 1e-9]):
        x = unscaled / mult
        if abs(x - round(x)) <= 0.06:
            chosen, raw = mult, int(round(x))
            break
    if chosen is None:
        return {"bar": bar, "before": score, "after": None, "after_max": None, "status": "unreconstructible",
                "mult": None, "raw": None, "floor": None}
    mult_note = "" if abs(chosen - regime_mult * conf) < 1e-9 else f"mult {chosen} inferred (regime-implied {regime_mult * conf:.2f} did not reproduce)"
    gap = _f(row.get("gap_pct")) or 0.0
    floor = resolve_conviction_floor(gap, row.get("catalyst_quality") or "", weights["conviction_floor"]["rules"])
    breakdown = None
    if row.get("score_breakdown"):
        try:
            breakdown = json.loads(row["score_breakdown"])
        except Exception:
            breakdown = None

    def present(r):
        return apply_output_scale(round(r * chosen, 1), scale)

    floor_bound_possible = floor is not None and raw == floor
    if breakdown and "conviction_floor" in breakdown:
        # exact: the stored components say how much the floor added
        comp = sum(v for k, v in breakdown.items() if k != "conviction_floor")
        raw_true = comp
        after = present(max(raw_true + 10, floor if floor is not None else -1e9))
        return {"bar": bar, "before": score, "after": after, "after_max": after, "status": "exact",
                "mult": chosen, "raw": raw_true, "floor": floor, "note": mult_note}
    if floor_bound_possible:
        # raw_true <= floor, unknown: after in [present(floor) .. present(floor + 10)]
        return {"bar": bar, "before": score, "after": None, "after_max": present(floor + 10),
                "status": "floor_bound_possible", "mult": chosen, "raw": raw, "floor": floor, "note": mult_note}
    after = present(max(raw + 10, floor if floor is not None else -1e9))
    return {"bar": bar, "before": score, "after": after, "after_max": after, "status": "ok",
            "mult": chosen, "raw": raw, "floor": floor, "note": mult_note}


def without_bonus(row: dict, eff: dict) -> float | None:
    """For a LISTED alert: the score it would have had WITHOUT the +10 (the 'depends on the +10'
    recount at the era bar)."""
    if eff.get("raw") is None:
        return None
    d = date.fromisoformat(row["alert_date"])
    sep = d >= SEPARATION_LIVE_FROM
    weights = SCORE_WEIGHTS if sep else SCORE_WEIGHTS_LEGACY
    raw_no = eff["raw"] - 10
    fl = eff["floor"]
    return apply_output_scale(round(max(raw_no, fl if fl is not None else -1e9) * eff["mult"], 1),
                              weights.get("output_scale"))


# ── stage 2 (paid, cached) ──────────────────────────────────────────────────────────────────
class Meter:
    def __init__(self):
        self.calls = 0
        self.in_tok = 0
        self.out_tok = 0
        self.seconds = 0.0

    async def log(self, *, model, caller, response):
        u = getattr(response, "usage", None)
        self.calls += 1
        self.in_tok += int(getattr(u, "input_tokens", 0) or 0) + int(getattr(u, "cache_read_input_tokens", 0) or 0) \
            + int(getattr(u, "cache_creation_input_tokens", 0) or 0)
        self.out_tok += int(getattr(u, "output_tokens", 0) or 0)


async def describe(ticker: str, desc_rows: dict, cache: dict) -> tuple[str, str | None]:
    from agents.market_intelligence.universe import TICKER_DESC
    r = desc_rows.get(ticker) or {}
    one = (r.get("description") or "").strip() or (TICKER_DESC.get(ticker) or "").strip()
    sector = (r.get("sector") or "").strip() or None
    if one:
        return one, sector
    if ticker in cache:
        return cache[ticker]["description"], cache[ticker]["sector"]
    from agents.market_intelligence.collector import get_fmp_profile
    p = await get_fmp_profile(ticker)
    d = str(p.get("description") or "").strip()[:300]
    s = (p.get("sector") or None) or sector
    cache[ticker] = {"description": d, "sector": s}
    return d, s


async def run_fits(jobs: list[dict], cache_path: Path, concurrency: int, meter: Meter) -> dict:
    """jobs: [{key, ticker, description, sector, themes}] -> {key: verdict dict}. Cached."""
    verdicts = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    todo = [j for j in jobs if j["key"] not in verdicts]
    print(f"stage 2: {len(jobs)} judgements, {len(jobs) - len(todo)} cached, {len(todo)} to buy")
    if not todo:
        return verdicts
    from agents.market_intelligence import theme_engine as te
    import agents.market_intelligence.spend_tracker as spend_mod

    async def _audit(*a, **k):
        return None
    te.log_audit_event = _audit
    spend_mod.log_anthropic_call_safe = meter.log
    sem = asyncio.Semaphore(concurrency)

    async def one(j):
        async with sem:
            t0 = time.monotonic()
            try:
                status, theme, why = await asyncio.wait_for(
                    te.judge_theme_fit(j["ticker"], description=j["description"], sector=j["sector"],
                                       themes=j["themes"]), timeout=60)
            except Exception as e:  # loud-ok: a replay job failing must not lose the batch
                status, theme, why = te.FIT_FAILED, None, f"exception: {e}"[:200]
            dt = time.monotonic() - t0
            meter.seconds += dt
            verdicts[j["key"]] = {"status": status, "theme": theme, "rationale": why, "seconds": round(dt, 2),
                                  "shortlist": [t["name"] for t in j["themes"]]}
            cache_path.write_text(json.dumps(verdicts, indent=1, sort_keys=True))
    await asyncio.gather(*(one(j) for j in todo))
    cache_path.write_text(json.dumps(verdicts, indent=1, sort_keys=True))
    return verdicts


# ── main ────────────────────────────────────────────────────────────────────────────────────
async def main_async(d: Path, spend: bool, concurrency: int) -> None:
    alerts, themes, desc_rows, closes = load(d)
    print(f"loaded {len(alerts)} alerts, {len(themes)} theme rows, {len(desc_rows)} descriptions, {len(closes)} close series")
    day_ctx: dict[date, DayContext] = {}
    rows: list[dict] = []
    for a in alerts:
        ad = date.fromisoformat(a["alert_date"])
        if ad not in day_ctx:
            day_ctx[ad] = DayContext(ad, board_as_of(themes, ad), closes)
        ctx = day_ctx[ad]
        t = a["ticker"].upper()
        read = etb.score_belonging(t, ctx.vec(t), ctx.baskets, ctx.listed)
        eff = score_effect(a)
        rows.append({"alert": a, "date": ad, "ticker": t, "read": read, "eff": eff, "ctx": ctx,
                     "stored_listed": _b(a.get("in_active_theme"))})

    # ── stage 1 report numbers
    n = len(rows)
    listed_recon = sum(1 for r in rows if r["read"].listed)
    listed_stored = sum(1 for r in rows if r["stored_listed"])
    agree = sum(1 for r in rows if bool(r["read"].listed) == bool(r["stored_listed"]))
    shortlisted = [r for r in rows if r["read"].fit_status == etb.FIT_PENDING]
    nascent_only = [r for r in rows if not r["read"].listed and r["read"].nascent_shortlist]
    n_paying = [r["ctx"].n_paying for r in rows]
    n_nas = [r["ctx"].n_nascent for r in rows]

    # ── stage 2 jobs
    desc_cache_path = d / "profile_descriptions.json"
    desc_cache = json.loads(desc_cache_path.read_text()) if desc_cache_path.exists() else {}
    jobs, nas_jobs, no_desc = [], [], []
    for r in shortlisted + nascent_only:
        pass
    for r in rows:
        rd = r["read"]
        if rd.listed:
            continue
        if not rd.shortlist and not rd.nascent_shortlist:
            continue
        description, sector = await describe(r["ticker"], desc_rows, desc_cache)
        desc_cache_path.write_text(json.dumps(desc_cache, indent=1, sort_keys=True))
        r["description"], r["sector"] = description, sector
        if not description:
            no_desc.append(r)
            continue
        if rd.shortlist:
            names = [nme for nme, _, _ in rd.shortlist]
            jobs.append({"key": f"{r['date']}|{r['ticker']}|paying|{';'.join(names)}", "ticker": r["ticker"],
                         "description": description, "sector": sector,
                         "themes": [r["ctx"].themes_by_name[nme] for nme in names if nme in r["ctx"].themes_by_name]})
        if rd.nascent_shortlist:
            names = [nme for nme, _, _ in rd.nascent_shortlist]
            nas_jobs.append({"key": f"{r['date']}|{r['ticker']}|nascent|{';'.join(names)}", "ticker": r["ticker"],
                             "description": description, "sector": sector,
                             "themes": [r["ctx"].themes_by_name[nme] for nme in names if nme in r["ctx"].themes_by_name]})
    from shared.llm_models import THEME_MODEL, pricing_for
    price = pricing_for(THEME_MODEL)
    est_per_call = EST_IN_TOK / 1e6 * price["input"] + EST_OUT_TOK / 1e6 * price["output"]
    est_total = (len(jobs) + len(nas_jobs)) * est_per_call
    cache_path = d / "fit_verdicts.json"
    cached = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    to_buy = [j for j in jobs + nas_jobs if j["key"] not in cached]
    print(f"stage 1: n={n} listed(recon)={listed_recon} listed(stored)={listed_stored} agree={agree} "
          f"shortlisted(unlisted, paying)={len(shortlisted)} nascent-shortlisted(unlisted)={len(nascent_only)} "
          f"no_description={len(no_desc)}")
    print(f"PRICE of stage 2 on {THEME_MODEL}: {len(jobs)} paying + {len(nas_jobs)} Nascent judgements "
          f"x ~US${est_per_call:.4f} = ~US${est_total:.2f} (cached already: {len(jobs) + len(nas_jobs) - len(to_buy)})")
    if not spend:
        print("dry run — pass --spend to buy stage 2 (verdicts are cached on run one).")
        _write(d, rows, {}, {}, None, price, THEME_MODEL, est_per_call, dry=True,
               stage1=(n, listed_recon, listed_stored, agree, shortlisted, nascent_only, no_desc, n_paying, n_nas))
        return
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY is not set — refusing to start stage 2")
    meter = Meter()
    verdicts = await run_fits(jobs, cache_path, concurrency, meter)
    # Nascent judgements ONLY for names not belonging at the paying stages (listed excluded above,
    # confirmed-at-paying excluded here) — the separate number.
    confirmed_paying = {j["key"].split("|")[0] + "|" + j["key"].split("|")[1]
                        for j in jobs if verdicts.get(j["key"], {}).get("status") == "confirmed"}
    nas_jobs = [j for j in nas_jobs if j["key"].split("|")[0] + "|" + j["key"].split("|")[1] not in confirmed_paying]
    verdicts = await run_fits(nas_jobs, cache_path, concurrency, meter)
    _write(d, rows, verdicts, {j["key"] for j in nas_jobs}, meter, price, THEME_MODEL, est_per_call, dry=False,
           stage1=(n, listed_recon, listed_stored, agree, shortlisted, nascent_only, no_desc, n_paying, n_nas))


def _write(d, rows, verdicts, nas_keys, meter, price, model, est_per_call, *, dry, stage1):
    n, listed_recon, listed_stored, agree, shortlisted, nascent_only, no_desc, n_paying, n_nas = stage1
    out = []
    P = out.append
    P(f"# Theme belonging backtest — two-stage rule (run {datetime.now().strftime('%Y-%m-%d %H:%M')})\n")
    P(f"n = {n} EP alerts. Board as-of each alert reconstructed from mi_themes (7-day recency, Retired dropped).\n")
    P("## Stage 1 — listed / shortlisted (correlation is a FILTER)\n")
    P("| | count | of |\n|---|---|---|")
    P(f"| listed on a paying-stage list (reconstructed as-of the alert day) | {listed_recon} | {n} |")
    P(f"| listed per the stored `in_active_theme` flag | {listed_stored} | {n} |")
    P(f"| reconstruction agrees with the stored flag | {agree} | {n} |")
    P(f"| unlisted AND shortlisted against a paying-stage basket at >= {etb.BELONGING_SHORTLIST_CORR_BAR} (= what correlation ALONE would have paid) | {len(shortlisted)} | {n} |")
    P(f"| unlisted with a Nascent shortlist | {len(nascent_only)} | {n} |")
    P(f"| shortlisted but no description anywhere (judgement refused) | {len(no_desc)} | {n} |")
    P(f"\nBaskets the max ran over, per alert: paying-stage mean {np.mean(n_paying):.1f} (min {min(n_paying)}, max {max(n_paying)}); "
      f"Nascent mean {np.mean(n_nas):.1f} (max {max(n_nas)}).\n")
    if dry:
        P(f"\n**Stage 2 not run (dry run).** Price: see stdout.\n")
        (d / "results.md").write_text("\n".join(out))
        return

    # ── stage 2 results
    def vkey(r, lane):
        names = [nme for nme, _, _ in (r["read"].shortlist if lane == "paying" else r["read"].nascent_shortlist)]
        return f"{r['date']}|{r['ticker']}|{lane}|{';'.join(names)}"

    for r in rows:
        rd = r["read"]
        v = verdicts.get(vkey(r, "paying")) if (not rd.listed and rd.shortlist) else None
        if v is None:
            r["fit"] = etb.with_fit(rd, etb.FIT_NO_DESCRIPTION if r in no_desc else etb.FIT_NOT_SHORTLISTED) \
                if not rd.listed and rd.shortlist else rd
        else:
            st = v["status"]
            stage = next((s for nme, s, _ in rd.shortlist if nme == v.get("theme")), None)
            r["fit"] = etb.with_fit(rd, st if st in (etb.FIT_CONFIRMED, etb.FIT_REJECTED) else etb.FIT_FAILED,
                                    v.get("theme"), stage, v.get("rationale"))
        nv = verdicts.get(vkey(r, "nascent")) if (not rd.listed and rd.nascent_shortlist) else None
        r["nascent_fit"] = nv
    confirmed = [r for r in rows if r["fit"].reason == "fit"]
    rejected = [r for r in rows if r["fit"].reason == "shortlisted_rejected"]
    unjudged = [r for r in rows if r["fit"].reason == "fit_unjudged"]
    belongs = [r for r in rows if r["fit"].belongs_paying]
    P("## Stage 2 — the fit judgement decides (theme_engine.judge_theme_fit, the nightly pass's own question)\n")
    P("| | count | of |\n|---|---|---|")
    P(f"| **list only (today's rule)** | **{listed_recon}** | {n} |")
    P(f"| shortlisted and CONFIRMED by the judgement | {len(confirmed)} | {len(shortlisted)} shortlisted |")
    P(f"| shortlisted and REJECTED by the judgement | {len(rejected)} | {len(shortlisted)} shortlisted |")
    P(f"| shortlisted, no verdict (no description / failed) -> list membership decides | {len(unjudged)} | {len(shortlisted)} shortlisted |")
    P(f"| **belonging = listed OR confirmed fit** | **{len(belongs)}** | {n} |")
    P(f"| **newly boosted (unlisted, confirmed)** | **{len(confirmed)}** | {n} |")
    P(f"| for reference — correlation ALONE at 0.35 would have newly boosted | {len(shortlisted)} | {n} |\n")

    # named cases
    P("## The named cases\n")
    P("| date | ticker | shortlist (theme @ corr) | verdict | rationale |\n|---|---|---|---|---|")
    named = sorted(NAMED_WRONG | NAMED_RIGHT | NAMED_HIGHS)
    for r in rows:
        k = (r["alert"]["alert_date"], r["ticker"])
        if k in NAMED_WRONG or k in NAMED_RIGHT:
            f = r["fit"]
            sl = ", ".join(f"{nme} @ {c:.2f}" for nme, _, c in r["read"].shortlist) or "(none — not shortlisted)"
            tag = "WRONG-CASE" if k in NAMED_WRONG else "MUST-WORK"
            verdict = ("LISTED" if f.listed else f"{f.fit_status}" + (f" → {f.fit_theme}" if f.fit_theme else ""))
            P(f"| {k[0]} | {k[1]} ({tag}) | {sl} | {verdict} | {(f.fit_rationale or '')[:160].replace('|', '/')} |")
    P("\nEvery confirmed fit (the newly boosted), with the judgement's own sentence:\n")
    P("| date | ticker | theme (stage) | corr | rationale |\n|---|---|---|---|---|")
    for r in sorted(confirmed, key=lambda r: (r["date"], r["ticker"])):
        f = r["fit"]
        c = next((c for nme, _, c in r["read"].shortlist if nme == f.fit_theme), None)
        P(f"| {r['date']} | {r['ticker']} | {f.fit_theme} ({f.fit_stage}) | {c:.2f} | {(f.fit_rationale or '')[:160].replace('|', '/')} |")

    # money path
    P("\n## Money path — alerts that would newly cross into HIGH\n")
    crossings, possible, unrecon = [], [], []
    for r in confirmed:
        e = r["eff"]
        if e["status"] == "unreconstructible":
            unrecon.append(r); continue
        if e["status"] == "floor_bound_possible":
            if e["before"] < e["bar"] <= e["after_max"]:
                possible.append(r)
            continue
        if e["before"] < e["bar"] <= e["after"]:
            crossings.append(r)
    P(f"Newly boosted alerts: {len(confirmed)}. Of those, already HIGH before the bonus (score >= its own era bar): "
      f"{sum(1 for r in confirmed if r['eff']['before'] >= r['eff']['bar'])}. Below the bar before: "
      f"{sum(1 for r in confirmed if r['eff']['before'] < r['eff']['bar'])}.\n")
    P(f"**Definite new HIGH crossings: {len(crossings)}.** Possible (conviction floor bound, raw unknown): {len(possible)}. "
      f"Unreconstructible score: {len(unrecon)}.\n")
    if crossings or possible:
        P("| date | ticker | theme | score before | score after | era bar | stored tier | note |\n|---|---|---|---|---|---|---|---|")
        for r in crossings + possible:
            e = r["eff"]
            after = e["after"] if e["after"] is not None else f"<= {e['after_max']}"
            P(f"| {r['date']} | {r['ticker']} | {r['fit'].fit_theme} | {e['before']} | {after} | {e['bar']} | {r['alert']['score_tier']} | "
              f"{'POSSIBLE — floor bound' if r in possible else 'crosses'} {e.get('note', '')} |")
    # the "4 HIGHs depend on the +10" recount
    P("\n### Recount: HIGHs that depend on the +10 TODAY (listed alerts, at each alert's own era bar)\n")
    dep = []
    for r in rows:
        if not r["read"].listed and not r["stored_listed"]:
            continue
        e = r["eff"]
        if e["status"] in ("unreconstructible",) or e["raw"] is None:
            continue
        if e["before"] >= e["bar"]:
            wo = without_bonus(r["alert"], e)
            if wo is not None and wo < e["bar"]:
                dep.append((r, wo))
    P(f"{len(dep)} listed alert(s) are HIGH only because of the +10 at their own era bar "
      f"(the earlier read of 4 — SNOW, HOOD 09-03; BLZE 07-31; AEHR 06-17 — was taken at a flat 70).\n")
    if dep:
        P("| date | ticker | score | without +10 | era bar |\n|---|---|---|---|---|")
        for r, wo in dep:
            P(f"| {r['date']} | {r['ticker']} | {r['eff']['before']} | {wo} | {r['eff']['bar']} |")
    P("\nThe four alerts the earlier read named, at their own era bar:\n")
    P("| date | ticker | score | listed | era bar | without +10 | HIGH without it? |\n|---|---|---|---|---|---|---|")
    for r in rows:
        k = (r["alert"]["alert_date"], r["ticker"])
        if k in NAMED_HIGHS:
            e = r["eff"]
            wo = without_bonus(r["alert"], e) if (r["read"].listed or r["stored_listed"]) else None
            P(f"| {k[0]} | {k[1]} | {e['before']} | {r['read'].listed or bool(r['stored_listed'])} | {e['bar']} | {wo if wo is not None else 'n/a (not listed)'} | "
              f"{'no' if (wo is not None and wo < e['bar']) else ('yes' if wo is not None else 'n/a')} |")

    # Nascent, separately
    P("\n## The Nascent question — SEPARATE number, not bundled\n")
    nas_conf = [r for r in rows if r.get("nascent_fit") and r["nascent_fit"]["status"] == "confirmed" and not r["fit"].belongs_paying]
    nas_judged = [r for r in rows if r.get("nascent_fit") and not r["fit"].belongs_paying]
    nas_cross = []
    for r in nas_conf:
        e = r["eff"]
        if e["status"] in ("ok", "exact") and e["before"] < e["bar"] <= e["after"]:
            nas_cross.append(r)
    P(f"Alerts NOT belonging under today's stage set that were judged against a Nascent shortlist: {len(nas_judged)}; "
      f"CONFIRMED against a Nascent theme: **{len(nas_conf)}** — the additional alerts that would carry the +10 if Nascent paid. "
      f"Of those, definite new HIGH crossings: {len(nas_cross)}.\n")
    if nas_conf:
        P("| date | ticker | Nascent theme | corr | score before | after | bar | rationale |\n|---|---|---|---|---|---|---|---|")
        for r in sorted(nas_conf, key=lambda r: (r["date"], r["ticker"])):
            v = r["nascent_fit"]; e = r["eff"]
            c = next((c for nme, _, c in r["read"].nascent_shortlist if nme == v["theme"]), None)
            P(f"| {r['date']} | {r['ticker']} | {v['theme']} | {c if c is None else f'{c:.2f}'} | {e['before']} | {e['after'] if e['after'] is not None else '?'} | {e['bar']} | {(v['rationale'] or '')[:120].replace('|', '/')} |")

    # cost
    P("\n## Cost of stage 2 (this run, cache misses only)\n")
    if meter and meter.calls:
        usd = meter.in_tok / 1e6 * price["input"] + meter.out_tok / 1e6 * price["output"]
        P(f"- model `{model}`; calls {meter.calls}; input tokens {meter.in_tok:,} (mean {meter.in_tok / meter.calls:,.0f}); "
          f"output tokens {meter.out_tok:,} (mean {meter.out_tok / meter.calls:,.0f}); **US${usd:.2f}** (US${usd / meter.calls:.4f} per call; "
          f"pre-run estimate US${est_per_call:.4f} per call); wall-clock {meter.seconds:.0f}s summed over calls, "
          f"mean {meter.seconds / meter.calls:.1f}s per call.")
    else:
        P("- no calls bought this run (all verdicts served from fit_verdicts.json).")
    days = len({r["date"] for r in rows})
    P(f"- per-scan-DAY load implied by this population: {len(shortlisted) / days:.2f} unlisted shortlisted ALERTS per alert day "
      f"({len(shortlisted)} over {days} alert days); the graded shortlist adds sub-bar names on top (see the live "
      f"`EP scan complete` line for the real count).")

    P("\n## Reconstruction honesty\n")
    st = Counter(r["eff"]["status"] for r in rows)
    P(f"- score arithmetic status over all {n} alerts: " + ", ".join(f"{k} {v}" for k, v in sorted(st.items())) + ".")
    P(f"- multiplier inferred (regime-implied did not reproduce): {sum(1 for r in rows if r['eff'].get('note'))}.")
    P("- 'exact' = the stored breakdown carried the floor; 'ok' = raw recovered as an integer with the floor not at the recovered "
      "value; 'floor_bound_possible' = the recovered raw equals an applicable floor, so the true raw may be lower (reported, never resolved).")
    P("- Descriptions: the nightly one-liner where one exists, else the yfinance profile paragraph fetched NOW (a company's business "
      "description is not price data, but it is the one input here that post-dates the alert).")
    (d / "results.md").write_text("\n".join(out))

    with (d / "per_alert.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["alert_date", "ticker", "ep_score", "score_tier", "stored_listed", "listed_recon", "best_theme", "best_corr",
                    "shortlist", "nascent_shortlist", "fit_status", "fit_theme", "fit_rationale", "belongs", "bar", "before",
                    "after", "after_max", "effect_status", "nascent_fit_status", "nascent_fit_theme", "n_paying_baskets", "n_nascent_baskets"])
        for r in rows:
            f = r["fit"]; e = r["eff"]; nv = r.get("nascent_fit") or {}
            w.writerow([r["date"], r["ticker"], r["alert"]["ep_score"], r["alert"]["score_tier"], r["stored_listed"], f.listed,
                        f.best_theme, f.best_corr, json.dumps(f.shortlist), json.dumps(f.nascent_shortlist), f.fit_status,
                        f.fit_theme, (f.fit_rationale or "")[:300], f.belongs_paying, e["bar"], e["before"], e["after"],
                        e["after_max"], e["status"], nv.get("status"), nv.get("theme"), r["ctx"].n_paying, r["ctx"].n_nascent])
    print("\n".join(out))
    print(f"\nwrote {d / 'results.md'}, {d / 'per_alert.csv'}, {d / 'fit_verdicts.json'}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dir")
    ap.add_argument("--spend", action="store_true", help="buy stage 2 (cached to fit_verdicts.json)")
    ap.add_argument("--concurrency", type=int, default=6)
    a = ap.parse_args()
    asyncio.run(main_async(Path(a.dir), a.spend, a.concurrency))


if __name__ == "__main__":
    main()
