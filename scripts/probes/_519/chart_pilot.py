"""#519 PILOT -- does reading the chart move the judge's call the RIGHT way on our own closed live trades?

Operator 2026-10-03: *"I want a cheaper option for now, unless we're certain this will help ep, I
don't want to spend that much now"* -> *"Pilot ok"*. The full chart-vision eval (~$42+) runs only if
this pilot shows the chart moving calls the right way.

WHAT IT DOES. Takes every CLOSED LIVE MAGNA53 trade (realized R is the scorer), and for each one
re-grades its alert through the holistic judge twice, ONE run each:
    arm B = judge + the candidate technical-structure instruction, NO chart   (text only)
    arm C = the SAME instruction + the point-in-time daily chart attached
Then scores each tier change C-vs-B by what the trade actually did: a WINNER (R > 0) the chart moved
UP, or a LOSER (R < 0) it moved DOWN, is "toward the right side"; the reverse is "the wrong side".
Arm A (no instruction at all) is not run -- the pilot asks only the C-minus-B question, the one
that says whether VISION adds anything beyond the free text instruction.

REUSE, NOT RE-IMPLEMENTATION. Everything that touches the judge is the eval's own code, imported:
`scripts/eval_chart_judge.py`'s alert-row SQL and its imports (chart render, payload build, profile
fetch), and `chart_axis.grade_b_c` (the shared B/C core -- the same bytes of instruction the live
EOD shadow and the full eval use). `eval_chart_judge.py` is NOT modified: the running image carries
the deployed copy, so a refactor of it would not exist there. The ~6-line per-row prep from
`eval_one` is repeated here call-for-call, and tests/test_519_chart_pilot.py pins that the call
sequence matches `eval_one`'s so the two cannot drift apart silently.

R is the repo's one definition: `total_pnl / kill_scale_bands.risk_placed(trade)` (#586) -- the risk
actually placed, NOT the pre-cap `risk_dollars`. Trades whose P&L a system bug distorted
(`pnl_attribution IS NOT NULL`) are not a clean scorer and are excluded, as the kill-scale cohort does.

THE LINE: measurement only. It never writes a trade, alert, strategy, sizing or safeguard row. The
only writes are the judge call's own telemetry, the same ones `eval_chart_judge.py` makes: one
`api_usage` cost row (bucket `chart_axis_pilot`) and one `judge_signal_trace` audit row per call.

PRE-DECLARED VERDICT RULE (written before any run; scored on TIER moves, trades with R == 0 unscored):
    helps     = at least 5 scored moves, AND right >= wrong + 3, AND right >= 2/3 of scored moves
    hurts     = the mirror image
    no signal = anything else
The p-value printed beside it (two-sided sign test vs a coin flip) says how easily noise alone
produces the split: with ONE judge run per arm, some B-vs-C changes are plain run-to-run noise.
EVERY verdict is DIRECTIONAL ONLY -- n is ~40 trades and there is no noise floor.

RUN (read-only; one process; ONE paid run -- capture it, never re-run to re-read):
    # 1. $0 -- prints population + cost estimate (renders every chart, calls no judge)
    docker exec -i apollo-market python - --dry-run < scripts/probes/_519/chart_pilot.py
    # 2. the paid run, captured ONCE: per-trade JSON lines -> stdout, summary -> stderr
    docker exec -i apollo-market python - < scripts/probes/_519/chart_pilot.py \\
        > /tmp/519_pilot.jsonl 2> /tmp/519_pilot.summary.txt

The cost estimate is printed BEFORE the first judge call and the run aborts above --max-usd
(default 5.00). A running spend counter also stops new calls if actual spend reaches --max-usd.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import statistics
import struct
import sys
from collections import Counter
from types import SimpleNamespace

# ordinal ranks. "mna" is a catalyst CATEGORY, not a level, so it is deliberately unranked: a move
# into or out of it has no direction.
TIER_RANK = {"none": 0, "MODERATE": 1, "HIGH": 2}
GRADE_RANK = {"routine": 1, "strong": 2, "game_changer": 3}

BIG_WIN_R = 2.0
BIG_LOSS_R = -1.0

# verdict thresholds (see the docstring -- declared before the run)
MIN_SCORED = 5
MIN_LEAD = 3

# cost-estimate constants. Source: docs/analysis/519_chart_vision_eval_cost_2026-09-12.md section 1:
# ~3.5 chars/token, ~285 tokens of forced-tool schema per call, image tokens = w*h/750, and a
# MEASURED 450-715 output tokens per judge call (the top of that band is used).
CHARS_PER_TOKEN = 3.5
EXPECTED_OUT_TOKENS = 715
DEFAULT_IMAGE_TOKENS = 1200           # used only if the PNG header cannot be read


# ── pure: direction scoring ──────────────────────────────────────────────────

def rank_move(rank_map: dict, b, c):
    """+1 if arm C ranks above arm B, -1 below, 0 equal; None when either side has no ranked
    value (a failed judge call returns no verdict; "mna" has no level)."""
    rb, rc = rank_map.get(b), rank_map.get(c)
    if rb is None or rc is None:
        return None
    return (rc > rb) - (rc < rb)


def score_move(r, move):
    """'right' | 'wrong' | None. A winner (R > 0) moved UP, or a loser (R < 0) moved DOWN, is
    'right'; the reverse is 'wrong'. None = no change, no verdict, or a break-even trade (R == 0)
    that has no side to be right or wrong about."""
    if move in (None, 0) or r is None or r == 0:
        return None
    if r > 0:
        return "right" if move > 0 else "wrong"
    return "right" if move < 0 else "wrong"


def sign_test_p(right: int, wrong: int) -> float:
    """Two-sided exact sign test of right-vs-wrong against a 50/50 coin. 1.0 when nothing scored."""
    n = right + wrong
    if n == 0:
        return 1.0
    k = min(right, wrong)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / (2 ** n)
    return min(1.0, 2 * tail)


def verdict_label(right: int, wrong: int) -> str:
    """'helps' | 'hurts' | 'no signal' by the pre-declared rule (integer arithmetic: no float edge)."""
    n = right + wrong
    if n >= MIN_SCORED:
        if right - wrong >= MIN_LEAD and 3 * right >= 2 * n:
            return "helps"
        if wrong - right >= MIN_LEAD and 3 * wrong >= 2 * n:
            return "hurts"
    return "no signal"


def tally(recs: list, key: str = "tier_move") -> dict:
    """Counts over `recs` (dicts carrying `r` and a move under `key`).
    graded = trades where both arms returned a usable value; changed = graded with a move."""
    graded = [x for x in recs if x.get(key) is not None]
    changed = [x for x in graded if x[key] != 0]
    scores = [score_move(x["r"], x[key]) for x in changed]
    right, wrong = scores.count("right"), scores.count("wrong")
    return {
        "trades": len(recs), "graded": len(graded), "changed": len(changed),
        "up": sum(1 for x in changed if x[key] > 0), "down": sum(1 for x in changed if x[key] < 0),
        "right": right, "wrong": wrong, "unscored": len(changed) - right - wrong,
    }


def summarize(recs: list, key: str = "tier_move") -> dict:
    """The whole scorecard: everything, big winners (R >= 2), big losers (R <= -1), the p-value,
    and the verdict -- all on the move named by `key`."""
    recs = [x for x in recs if x.get("r") is not None]
    allt = tally(recs, key)
    return {
        "all": allt,
        "big_winners": tally([x for x in recs if x["r"] >= BIG_WIN_R], key),
        "big_losers": tally([x for x in recs if x["r"] <= BIG_LOSS_R], key),
        "p_value": sign_test_p(allt["right"], allt["wrong"]),
        "verdict": verdict_label(allt["right"], allt["wrong"]),
    }


def verdict_line(summary: dict, n_trades: int) -> str:
    a = summary["all"]
    return (f"VERDICT (DIRECTIONAL ONLY, n={n_trades} trades, one judge run per arm): chart "
            f"{summary['verdict'].upper()} -- it changed {a['changed']} of {a['graded']} calls; "
            f"{a['right']} moved toward the right side, {a['wrong']} toward the wrong side"
            f"{f', {a['unscored']} on break-even trades (no side)' if a['unscored'] else ''}; "
            f"coin-flip noise alone gives a split at least this uneven {summary['p_value']:.0%} of the time.")


# ── pure: population ─────────────────────────────────────────────────────────

def realized_r(trade: dict, risk_fn):
    """total_pnl / the risk actually placed (kill_scale_bands.risk_placed -- #586, the repo's one
    definition of R). None when either side is missing or the risk is not positive."""
    pnl = trade.get("total_pnl")
    risk = risk_fn(trade)
    if pnl is None or risk is None or risk <= 0:
        return None
    return float(pnl) / risk


def split_population(rows: list, risk_fn) -> dict:
    """Closed live trades -> the scored population + exactly what was left out and why."""
    by_signal = Counter(r.get("signal_type") or "(none)" for r in rows)
    magna = [r for r in rows if r.get("signal_type") == "magna53"]
    attributed = [r for r in magna if r.get("pnl_attribution") is not None]
    clean = [r for r in magna if r.get("pnl_attribution") is None]
    eligible, no_risk = [], []
    for r in clean:
        r = dict(r)
        r["r"] = realized_r(r, risk_fn)
        (eligible if r["r"] is not None else no_risk).append(r)
    return {"closed_live_total": len(rows), "by_signal": by_signal, "magna53": len(magna),
            "bug_distorted": len(attributed), "no_risk": len(no_risk), "eligible": eligible}


def r_distribution(rs: list) -> dict:
    if not rs:
        return {"n": 0}
    return {
        "n": len(rs), "mean": statistics.mean(rs), "median": statistics.median(rs),
        "min": min(rs), "max": max(rs),
        "winners": sum(1 for r in rs if r > 0), "losers": sum(1 for r in rs if r < 0),
        "flat": sum(1 for r in rs if r == 0),
        "big_winners": sum(1 for r in rs if r >= BIG_WIN_R),
        "big_losers": sum(1 for r in rs if r <= BIG_LOSS_R),
    }


def population_lines(pop: dict) -> list:
    rows = pop["eligible"]
    d = r_distribution([x["r"] for x in rows])
    sig = ", ".join(f"{k}:{v}" for k, v in sorted(pop["by_signal"].items()))
    lines = [
        "POPULATION -- closed LIVE trades (realized R = total_pnl / risk actually placed)",
        f"  closed live trades, all setups: {pop['closed_live_total']}  [{sig}]",
        f"  MAGNA53: {pop['magna53']}  -> left out: {pop['bug_distorted']} with P&L distorted by a "
        f"system bug (pnl_attribution set), {pop['no_risk']} with no usable risk figure",
        f"  SCORED POPULATION: {d['n']} trades",
    ]
    if d["n"]:
        dates = sorted(x["alert_date"] for x in rows)
        lines += [
            f"  alert dates: {dates[0]} .. {dates[-1]}",
            f"  R: mean {d['mean']:+.2f}  median {d['median']:+.2f}  worst {d['min']:+.2f}  "
            f"best {d['max']:+.2f}",
            f"  {d['winners']} winners (R>0), {d['losers']} losers (R<0), {d['flat']} break-even; "
            f"{d['big_winners']} big winners (R>={BIG_WIN_R:g}), {d['big_losers']} big losers "
            f"(R<={BIG_LOSS_R:g})",
        ]
    return lines


# ── pure: cost ───────────────────────────────────────────────────────────────

def est_tokens(chars: int) -> int:
    return int(chars / CHARS_PER_TOKEN) + 1


def png_dims(png: bytes):
    """(width, height) from the PNG IHDR chunk, or None when it is not a readable PNG."""
    if png and len(png) >= 24 and png[:8] == b"\x89PNG\r\n\x1a\n":
        return struct.unpack(">II", png[16:24])
    return None


def image_tokens(png: bytes) -> int:
    dims = png_dims(png)
    return int(dims[0] * dims[1] / 750) if dims else DEFAULT_IMAGE_TOKENS


def estimate_run(items: list, price: dict, *, schema_chars: int, max_out: int,
                 expected_out: int = EXPECTED_OUT_TOKENS) -> dict:
    """items: one dict per trade with b_chars (prompt + text note), c_chars (prompt + chart note),
    img_tokens. Two calls per trade (B, C). `expected` uses the measured output-token level;
    `worst` assumes every call fills max_tokens."""
    schema = est_tokens(schema_chars)
    in_tok = sum(est_tokens(i["b_chars"]) + schema + est_tokens(i["c_chars"]) + schema
                 + i["img_tokens"] for i in items)
    calls = 2 * len(items)

    def usd(out_per_call):
        return (in_tok * price["input"] + calls * out_per_call * price["output"]) / 1e6

    return {"calls": calls, "in_tokens": in_tok, "expected_usd": usd(expected_out),
            "worst_usd": usd(max_out), "expected_out_per_call": expected_out,
            "max_out_per_call": max_out}


class BudgetExceeded(RuntimeError):
    """Raised by the spend tap once actual spend reaches the cap; the judge fails open on it."""


class SpendTap:
    """Wraps the factory client. Counts tokens + dollars on every response and refuses new calls
    once `max_usd` is reached. Only `.messages.create` / `.close` are used by the judge."""

    def __init__(self, client, cost_fn, max_usd: float):
        self._client, self._cost_fn, self.max_usd = client, cost_fn, max_usd
        self.calls = self.in_tok = self.out_tok = 0
        self.usd = 0.0
        self.models = set()
        self.messages = SimpleNamespace(create=self._create)

    @property
    def over_budget(self) -> bool:
        return self.usd >= self.max_usd

    async def _create(self, **kw):
        if self.over_budget:
            raise BudgetExceeded(f"spend ${self.usd:.2f} reached the ${self.max_usd:.2f} cap")
        resp = await self._client.messages.create(**kw)
        u = getattr(resp, "usage", None)
        i, o = int(getattr(u, "input_tokens", 0) or 0), int(getattr(u, "output_tokens", 0) or 0)
        cc = int(getattr(u, "cache_creation_input_tokens", 0) or 0)
        cr = int(getattr(u, "cache_read_input_tokens", 0) or 0)
        self.calls += 1
        self.in_tok += i + cc + cr
        self.out_tok += o
        self.models.add(kw.get("model"))
        self.usd += self._cost_fn(kw.get("model"), i, o, cc, cr)
        return resp

    async def close(self):
        await self._client.close()


# ── runtime (lazy: needs the prod image) ─────────────────────────────────────

def _ensure_app_on_path():
    # `python -` puts the working directory first on sys.path; make the app root importable even
    # if the exec landed somewhere else.
    for d in ("/app", os.getcwd()):
        if os.path.isdir(os.path.join(d, "shared")) and d not in sys.path:
            sys.path.insert(0, d)


def _load_runtime() -> SimpleNamespace:
    """Every import that needs the prod image (DB pool, mplfinance, the Anthropic SDK). Kept out
    of module scope so the pure parts above import anywhere (the unit tests)."""
    # a probe's failures must never page as if they were live (agents/market_intelligence/llm_health)
    os.environ.setdefault("APOLLO_CALL_ORIGIN", "probe")
    _ensure_app_on_path()
    from scripts import eval_chart_judge as ev          # the eval's own imports + SQL, unmodified
    from agents.market_intelligence import chart_axis
    from agents.market_intelligence import ep_grade_judge as judge
    from agents.market_intelligence.db import get_pool
    from agents.market_intelligence.kill_scale_bands import risk_placed
    from shared.llm_client import make_async_anthropic   # the adapter: opus-5-5 rejects forced tool_choice
    from shared.llm_models import pricing_for
    from shared.output_ceilings import max_tokens_for
    try:
        from shared.llm_models import cost_for_call
    except ImportError:                                  # an image older than 2026-09-26
        cost_for_call = None
    try:
        from shared.llm_samples import capture_disabled
    except ImportError:
        import contextlib
        capture_disabled = contextlib.nullcontext
    return SimpleNamespace(
        ALERT_ROW_SQL=ev._ALERT_ROW_SQL, render_prior_day_chart=ev.render_prior_day_chart,
        fetch_profile=ev.fetch_profile, resolve_grounded_text=ev.resolve_grounded_text,
        build_judge_payload=ev.build_judge_payload, grade_b_c=ev.grade_b_c,
        note_b=chart_axis.CHART_AXIS_NOTE_TEXT_ONLY, note_c=chart_axis.CHART_AXIS_NOTE,
        build_prompt=judge._build_judge_prompt, judge_tool=judge._judge_tool, MODEL=judge.MODEL,
        get_pool=get_pool, risk_placed=risk_placed, make_client=make_async_anthropic,
        pricing_for=pricing_for, max_out=max_tokens_for("ep_grade_judge"),
        cost_for_call=cost_for_call, capture_disabled=capture_disabled)


_TRADES_SQL = """
SELECT id, ticker, alert_date, signal_type, pnl_attribution, total_pnl, risk_dollars_actual,
       entry_shares, entry_price, hard_stop
FROM mi_live_trades
WHERE status = 'closed' AND account_mode = 'live'
ORDER BY alert_date ASC, id ASC
"""


async def prepare_trade(pool, trade: dict, rt) -> dict:
    """Per-row prep -- call-for-call the same as eval_chart_judge.eval_one's (pinned by
    tests/test_519_chart_pilot.py): alert row -> point-in-time chart -> profile -> grounded text
    -> payload. Read-only. Returns a skip record or the judge inputs."""
    ticker, alert_date = trade["ticker"], trade["alert_date"]
    async with pool.acquire() as conn:      # held for the one SELECT only, not through the render
        row = await conn.fetchrow(rt.ALERT_ROW_SQL, ticker, alert_date)
    if row is None:
        return {"skip": "no_alert_row"}
    png, n_daily = await rt.render_prior_day_chart(ticker, alert_date)
    if png is None:
        return {"skip": "no_chart", "n_daily": n_daily}
    mc, sector, company = await rt.fetch_profile(ticker)
    grounded_text, _ = await rt.resolve_grounded_text(dict(row), company, grounded=False)
    payload, _ = rt.build_judge_payload(dict(row), grounded_text, mc, sector)
    return {"row": row, "png": png, "n_daily": n_daily, "payload": payload}


def _arm(v):
    if not v:
        return None
    return {"tier": v.get("tier"), "grade": v.get("grade"),
            "direction": v.get("direction_vs_floor"), "confidence": v.get("confidence"),
            "rationale": (v.get("rationale") or "")[:240]}


def make_record(trade: dict, prep: dict, bc: dict | None) -> dict:
    """One JSON line's worth: the trade, what each arm said, and how the chart moved the call."""
    rec = {"trade_id": trade["id"], "ticker": trade["ticker"], "alert_date": str(trade["alert_date"]),
           "r": round(trade["r"], 3)}
    if "skip" in prep:
        return {**rec, "skip": prep["skip"], "n_daily": prep.get("n_daily")}
    b, c = _arm((bc or {}).get("b_verdict")), _arm((bc or {}).get("c_verdict"))
    rec["floor_tier"] = prep["row"]["floor_tier"]
    rec.update(b=b, c=c)
    rec["tier_move"] = rank_move(TIER_RANK, b and b["tier"], c and c["tier"])
    rec["grade_move"] = rank_move(GRADE_RANK, b and b["grade"], c and c["grade"])
    rec["score"] = score_move(trade["r"], rec["tier_move"])
    if b is None or c is None:
        rec["failed"] = "no verdict from " + " and ".join(
            n for n, a in (("B", b), ("C", c)) if a is None)
    return rec


def _fmt(s, name):
    a, w, u = s["right"], s["wrong"], s["unscored"]
    return (f"  {name:<22} n={s['trades']:<3} graded={s['graded']:<3} changed={s['changed']:<3} "
            f"(up {s['up']}, down {s['down']})  right side={a}  wrong side={w}"
            + (f"  break-even={u}" if u else ""))


async def run(args, *, rt=None, out=None, err=None) -> int:
    out, err = out or sys.stdout, err or sys.stderr

    def say(*lines):
        for ln in lines:
            print(ln, file=err, flush=True)

    rt = rt or _load_runtime()

    pool = await rt.get_pool()
    try:
        async with pool.acquire() as conn:
            rows = [dict(r) for r in await conn.fetch(_TRADES_SQL)]
        pop = split_population(rows, rt.risk_placed)
        say("=" * 78, "#519 CHART PILOT -- does the chart move the judge's call the right way?", "",
            *population_lines(pop))
        trades = pop["eligible"]
        if not trades:
            say("  nothing to grade -- no scored population.")
            return 2

        # phase 1: prepare every trade (DB reads + chart render, $0). A dry run stops after pricing.
        prep_sem = asyncio.Semaphore(4)

        async def _prep(t):
            async with prep_sem:
                try:
                    return await prepare_trade(pool, t, rt)
                except Exception as e:  # a bad row is a skip, never a crash
                    return {"skip": f"prep_error: {type(e).__name__}: {str(e)[:120]}"}

        preps = await asyncio.gather(*[_prep(t) for t in trades])
        skips = Counter(p["skip"].split(":")[0] for p in preps if "skip" in p)
        ready = [(t, p) for t, p in zip(trades, preps) if "skip" not in p]
        say(f"  SKIPPED before any judge call: {sum(skips.values())} of {len(trades)}"
            + (f"  [{', '.join(f'{k}:{v}' for k, v in sorted(skips.items()))}]" if skips else ""),
            f"  GRADABLE: {len(ready)} trades",
            "  alert floor tier of the gradable: "
            + str(dict(Counter(p["row"]["floor_tier"] for _, p in ready))))
        for t, p in zip(trades, preps):
            if "skip" in p:
                say(f"    ~ {t['ticker']:6} {t['alert_date']}  skip={p['skip']}"
                    + (f" (n_daily={p['n_daily']})" if p.get("n_daily") is not None else ""))
        if not ready:
            say("  nothing gradable.")
            return 2

        model = rt.MODEL
        price = rt.pricing_for(model)
        schema_chars = len(json.dumps(rt.judge_tool(False)))
        items = []
        for _, p in ready:
            base = len(rt.build_prompt(p["payload"]))
            items.append({"b_chars": base + 1 + len(rt.note_b), "c_chars": base + 1 + len(rt.note_c),
                          "img_tokens": image_tokens(p["png"])})
        est = estimate_run(items, price, schema_chars=schema_chars, max_out=rt.max_out)
        say("",
            f"COST ESTIMATE (before any judge call): {est['calls']} calls on {model} "
            f"(${price['input']:g}/${price['output']:g} per Mtok in/out, from pricing_for)",
            f"  expected ~${est['expected_usd']:.2f}  [~{est['in_tokens']:,} input tokens + "
            f"~{est['expected_out_per_call']} output/call, the measured level]",
            f"  worst case ${est['worst_usd']:.2f}  [every call fills its {est['max_out_per_call']}"
            f"-token ceiling]  -- the abort limit ${args.max_usd:.2f} is checked against the EXPECTED "
            "figure; actual spend is also capped at it as the run goes")
        if est["expected_usd"] > args.max_usd:
            say(f"ABORT: expected ${est['expected_usd']:.2f} exceeds --max-usd {args.max_usd:.2f}. "
                "Nothing was spent.")
            return 3
        if args.dry_run:
            say("DRY RUN -- no judge call made, nothing spent.", "=" * 78)
            return 0
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            say("ABORT: ANTHROPIC_API_KEY is not set in this process. Nothing was spent.")
            return 2

        # phase 2: the paid calls. One grade_b_c (replicates=1) per trade = arm B once + arm C once.
        client = rt.make_client(api_key=key)
        tap = SpendTap(client, rt.cost_for_call or (
            lambda m, i, o, cc, cr: (i * price["input"] + o * price["output"]) / 1e6), args.max_usd)
        api_sem = asyncio.Semaphore(3)
        records: list = []

        async def grade(t, p):
            if tap.over_budget:
                return make_record(t, p, None) | {"failed": "spend cap reached before this trade"}
            bc = await rt.grade_b_c(tap, api_sem, p["payload"], p["png"], 1,
                                    log_caller="chart_axis_pilot")
            return make_record(t, p, bc)

        def emit(rec):
            records.append(rec)
            print(json.dumps(rec, default=str), file=out, flush=True)

        try:
            with rt.capture_disabled():
                # canary: the first trade alone. A judge that returns nothing here is an adapter /
                # model / API problem, and finding that out on one trade is the cheap way.
                first_t, first_p = ready[0]
                first = await grade(first_t, first_p)
                emit(first)
                if first.get("failed") and first.get("b") is None and first.get("c") is None:
                    say("ABORT: the judge returned NO verdict on the first trade for either arm -- "
                        "an adapter / model / API problem (the cause is in the WARNING lines above). "
                        f"Calls made: {tap.calls}, spend ${tap.usd:.3f}.")
                    return 4
                trade_sem = asyncio.Semaphore(3)

                async def _one(t, p):
                    async with trade_sem:
                        emit(await grade(t, p))

                await asyncio.gather(*[_one(t, p) for t, p in ready[1:]])
        finally:
            try:
                await tap.close()
            except Exception:  # loud-ok: closing a finished client must not mask the result
                pass
        for t, p in zip(trades, preps):                  # skipped trades get a line too
            if "skip" in p:
                emit(make_record(t, p, None))

        # the scorecard
        graded = [r for r in records if "skip" not in r]
        scored = summarize(graded, "tier_move")
        grades = summarize(graded, "grade_move")
        failed = [r for r in graded if r.get("failed")]
        b_mix = Counter((r["b"] or {}).get("tier") for r in graded if r.get("b"))
        c_mix = Counter((r["c"] or {}).get("tier") for r in graded if r.get("c"))
        say("", "=" * 78, "RESULT -- arm C (instruction + chart) vs arm B (instruction only), one run each",
            f"  trades judged: {len(graded)}   judge returned nothing on at least one arm: {len(failed)}",
            f"  tier mix  B: {dict(b_mix)}   C: {dict(c_mix)}", "",
            "TIER MOVES (primary) -- right side = a winner moved up or a loser moved down",
            _fmt(scored["all"], "all trades"),
            _fmt(scored["big_winners"], f"big winners (R>={BIG_WIN_R:g})"),
            _fmt(scored["big_losers"], f"big losers (R<={BIG_LOSS_R:g})"), "",
            "GRADE MOVES (secondary -- routine < strong < game_changer; 'mna' unranked)",
            _fmt(grades["all"], "all trades"),
            _fmt(grades["big_winners"], f"big winners (R>={BIG_WIN_R:g})"),
            _fmt(grades["big_losers"], f"big losers (R<={BIG_LOSS_R:g})"), "",
            verdict_line(scored, len(graded)), "",
            f"SPEND: estimated ${est['expected_usd']:.2f} (worst ${est['worst_usd']:.2f}), "
            f"ACTUAL ${tap.usd:.2f} over {tap.calls} calls ({tap.in_tok:,} in / {tap.out_tok:,} out "
            f"tokens)  [use this to size the full run]")
        if tap.models and tap.models != {model}:
            say(f"  WARNING: calls ran on {sorted(map(str, tap.models))} but were priced as {model}.")
        for r in failed:
            say(f"  ~ no verdict: {r['ticker']:6} {r['alert_date']}  {r['failed']}")
        changed = [r for r in graded if r.get("tier_move")]
        if changed:
            say("", "CHANGED CALLS (tier) -- for the operator to look at")
            for r in sorted(changed, key=lambda x: x["alert_date"]):
                say(f"  {r['ticker']:6} {r['alert_date']}  R={r['r']:+.2f}  "
                    f"B={r['b']['tier']} -> C={r['c']['tier']}  [{r['score'] or 'break-even'}]")
        if args.outdir:
            os.makedirs(args.outdir, exist_ok=True)
            by_id = {t["id"]: p for t, p in zip(trades, preps)}
            for r in changed:
                with open(os.path.join(args.outdir, f"{r['ticker']}_{r['alert_date']}.png"), "wb") as f:
                    f.write(by_id[r["trade_id"]]["png"])
            say(f"  charts of the changed calls saved to {args.outdir}/ (inside the container)")
        say("SUMMARY_JSON " + json.dumps({"tier": scored, "grade": grades, "n_graded": len(graded),
                                          "failed": len(failed), "spend_usd": round(tap.usd, 4),
                                          "calls": tap.calls}, default=str),
            "=" * 78)
        return 0
    finally:
        try:
            await pool.close()
        except Exception:  # loud-ok: a probe's pool teardown is not a result
            pass


def main(argv=None) -> int:
    import logging      # the judge fails open and only LOGS why -- surface those warnings on stderr
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr,
                        format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true",
                    help="load the population, render the charts, print the cost estimate; call no judge")
    ap.add_argument("--max-usd", type=float, default=5.0,
                    help="abort if the EXPECTED estimate exceeds this; also caps actual spend")
    ap.add_argument("--outdir", default="",
                    help="optional folder (inside the container) for the PNGs of the changed calls")
    return asyncio.run(run(ap.parse_args(argv)))


if __name__ == "__main__":
    sys.exit(main())
