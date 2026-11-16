"""Breakout v1 — the NIGHTLY LIST (component B2) and its one Telegram message (B3), PAPER setup phase 1. No orders.

The rules are `breakout_v1.py` (PURE); this module is the plumbing around them for ONE night D = today:
  1. universe bars from `mi_daily_closes` (`db.cb_get_universe_bars`, the shadow's SQL prefilter at the v1 floors:
     close >= $2 today, median dollar volume over the last 20 sessions >= 0.7 x $5M — a deliberate SUPERSET, the module
     stays the authority), indexed on SPY's calendar (`consolidation_breakout_shadow.build_series`);
  2. the TYPE half of the universe from `mi_security_types` (type + Polygon's stored name): common stock, ADRs and
     SINGLE-ASSET funds (`breakout_v1.security_admitted` / `fund_rule`); a fund with no stored name is EXCLUDED (fail
     closed) and counted; a ticker whose stored history crosses an UNAPPLIED split sits out (two price scales);
  3. the RS cross-section over EVERY security at the v1 floors (raw close >= $2, 20-session median dollar volume >= $5M,
     a 63-session return known over consecutive sessions), funds and ETFs included — `cb.cross_section_one_date`'s
     rs_best. His ruling 2026-10-29 ("Ok a"): the pool the approved 12-of-24 check ranked against; the TYPE rule decides
     only who may be LISTED (a pool-only member is ranked, never given the gates);
  4. `breakout_v1.v1_gates` per member with the 86-session consecutive history; every name passing every gate is a row
     of `mi_breakout_v1_list` (the night's rows replaced whole — idempotent). THREE rankings are computed and stored
     on every row every night (`rank_all`): the PICK MODEL score (`breakout_v1_pick_model.py`, the live order since
     2026-11-14, his "pick model, let's continue to eval and keep all the old models we have as backup"), the ORDER
     SCORE (`rank_rows`, the order from 2026-11-02 to 2026-11-14, unchanged;
     `docs/analysis/cb_rebuild_from_qm_trades_2026-11-02.md` §2) and the 20-session DOLLAR VOLUME. ONE switch picks
     which of them sets `list_rank` — the order the paper slots follow (`get_ranking`:
     `mi_safeguard_state('breakout_v1_ranking', 'global')`, no row = the pick model; flipped with one SQL statement,
     no deploy; it acts from the next list write);
  5. ONE audit row `breakout_v1_list_run` (universe size, funds kept / excluded and why, names passing, per-gate fail
     counts — the three CONTEXT checks of 2026-11-14 among them — the names those checks alone took off the list
     (`context_removed`), the ranking that set the order and all three scores per name (`ranking`), the message's
     fate);
  6. ONE paper-prefixed Telegram message: tonight's TOP 10 by the selected ranking (ticker, level, score, rs_best) and
     the night's total count (the rebuilt list holds ~250 names a night — never 250 lines) — ONLY when the list is
     non-empty (an alert that says no action is noise). A failed send is logged and counted in the audit row.

THE LINE. A LIST and a GRADE only: this module writes `mi_breakout_v1_list` and `mi_audit_log` (through
`log_audit_event`), imports nothing from `broker/`, writes no trade table and no `mi_strategies` row, prepares no
order. No entry / sizing / order / safeguard path reads the list in phase 1.

Fails OPEN under `BUDGET_S` (a `breakout_v1_list_error` audit row, no raise; the next night rebuilds its own list);
a crash is re-raised AFTER the audit row so `audit_wrap`'s `notify_job_failure` is the one page.
Owner doc: docs/setups/consolidation_breakout.md (2026-10-29 "breakout v1 PHASE 1 BUILT"; 2026-11-02 the rebuilt
rules + the order score; 2026-11-14 the pick model orders the list, the older rankings kept as backups).
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import Counter
from datetime import date
from typing import Optional

from agents.market_intelligence import breakout_v1 as bv
from agents.market_intelligence import breakout_v1_pick_model as pm
from agents.market_intelligence import consolidation_breakout as cb
from agents.market_intelligence.consolidation_breakout_shadow import _json_safe, build_series
from agents.market_intelligence.db import (
    BREAKOUT_V1_PAPER_TOGGLE,
    BREAKOUT_V1_PAPER_TOGGLE_ENV,
    bv1_get_security_types_named,
    bv1_replace_list,
    cb_get_calendar,
    cb_get_sic,
    cb_get_universe_bars,
    get_runtime_toggle,
    get_safeguard_state,
    get_unapplied_splits,
    log_audit_event,
)

logger = logging.getLogger(__name__)

JOB_ID = "breakout_v1_list"
AUDIT_RUN_EVENT = "breakout_v1_list_run"
AUDIT_ERROR_EVENT = "breakout_v1_list_error"
BUDGET_S = 600                        # fail open past this (the shadow's pattern; a night is ~1 minute of work)
# Bars loaded per name: the 6-month move reads 126 highs, each against the lowest low of the 64 sessions up to it, so
# 189 sessions are needed for the research's full look-back (`breakout_v1.runup6m_at`; 150 shortened it), + margin.
# The EMA21 is seeded at the first loaded bar (its weight at D after 200 bars is ~1e-8). The three context checks
# (2026-11-14) need at most 189 bars (the lower line's chart height; 126 + 1 for the 6-month return, 60 for the 50-day
# 10 sessions back) and read the research's last-200-bar window, so the load did NOT change: a name with more than 11
# calendar holes in these 200 sessions reads "insufficient_history" on the lower line where the research scored it.
HISTORY_SESSIONS = 200
CALENDAR_SESSIONS = 400
PREFILTER_DOLLAR_VOL = 0.7 * bv.MIN_DOLLAR_VOL
SCAN_CHUNK = 250                      # tickers per to_thread slice: cancellation lands between slices
FUND_EXCLUDED_LIST_MAX = 60           # fund tickers named in the audit row, per reason
CONTEXT_REMOVED_LIST_MAX = 60         # names a context check took off the list, named in the audit row, per check
SHORT_FALLBACK_LIST_MAX = 60          # names whose 52-week facts came off the short bars, named in the audit row
MESSAGE_TOP_N = 10                    # the nightly message and bare /bgrade show the top 10 by list rank
# The list's ORDER (operator-signed 2026-11-14: "pick model, let's continue to eval and keep all the old models we have
# as backup"). All three are computed and stored every night; the switch only picks which one sets `list_rank`.
RANKING_PICK_MODEL, RANKING_ORDER_SCORE, RANKING_DOLLAR_VOLUME = "pick_model", "order_score", "dollar_volume"
RANKINGS = (RANKING_PICK_MODEL, RANKING_ORDER_SCORE, RANKING_DOLLAR_VOLUME)
DEFAULT_RANKING = RANKING_PICK_MODEL
RANKING_SWITCH = "breakout_v1_ranking"      # mi_safeguard_state(safeguard, 'global').state = one of RANKINGS
RANKING_READ_TRIES = 3                      # a failed switch read is retried (a transient miss must not un-flip a backup)
RANKING_READ_PAUSE_S = 1.0
RANKING_READ_TIMEOUT_S = 10.0               # asyncpg's own bound per try: a hung read must not eat the job's 600 s budget
RANKING_SCORE_COL = {RANKING_PICK_MODEL: "pick_score", RANKING_ORDER_SCORE: "order_score",
                     RANKING_DOLLAR_VOLUME: "dollar_vol20"}
RANKING_RANK_COL = {k: "rank_" + k for k in RANKINGS}
# The grade cutoffs on `pick_score` (the pick model's log-odds). FROZEN 2026-11-15 from
# scripts/probes/_717_grades_1115/cutoffs.json (calibrated buy rate >= 4x / 2x / 1x the 2017-2020 fit base rate);
# approved by the operator 2026-11-15 ("grades look good"). A label only: it orders nothing and removes nothing.
GRADE_CUTOFFS = (("A+", -3.4942), ("A", -4.1845), ("B", -4.8715))
GRADE_ORDER = ("A+", "A", "B", "C")


def grade_for(score) -> Optional[str]:
    """A+ / A / B / C from a pick score; None when there is no score."""
    if score is None:
        return None
    for g, cut in GRADE_CUTOFFS:
        if score >= cut:
            return g
    return "C"
RANKING_LABEL = {RANKING_PICK_MODEL: "the pick model", RANKING_ORDER_SCORE: "the order score",
                 RANKING_DOLLAR_VOLUME: "dollar volume"}
AUDIT_HEADROOM = 2000                 # chars kept free under mi_audit_log's detail budget (`fit_audit_detail`)
AUDIT_SCORE_DP = 4                    # decimals of the per-name scores in the audit row
AUDIT_SCORES_MAX = 300                # names whose three scores ride in the audit row (by list_rank; mi_audit_log's
                                      # detail budget is 32,000 chars and a busy night lists 1,000+ names). EVERY name's
                                      # scores and ranks are on its mi_breakout_v1_list row — that table is the record.


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# Pure plumbing (unit-tested without a database)
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def scan_members(series: dict, *, today_ci: int, types: dict, unapplied: set) -> dict:
    """Tonight's RS-pool members and their facts. `series` = {ticker: (DailyBars, cidx)}, `types` = {ticker:
    (security_type, name)}. Returns {"members": [...], "counts": Counter, "fund_kept": [...], "fund_excluded":
    {reason: [...]}}. A member passes the $2 / $5M floors at D and has a 63-session return over consecutive sessions —
    whatever its type (the RS pool, his 2026-10-29 ruling (a)); `listable` says whether its TYPE admits it to the list
    (stock, ADR, unknown type, kept single-asset fund); `history` says whether the 86-session data guard holds. Only a
    listable member with history gets the gates. Bad tickers / test symbols are out of both."""
    members, counts = [], Counter()
    fund_kept, fund_excl = [], {}
    for ticker, (bars, cidx) in series.items():
        D = len(bars) - 1
        if int(cidx[-1]) != today_ci:
            counts["no_bar_today"] += 1
            continue
        st, name = types.get(ticker, (None, None))
        ok, why = bv.security_admitted(ticker, st, name)
        if st == bv.FUND_SECURITY_TYPE:
            if ok:
                fund_kept.append(ticker)
            else:
                fund_excl.setdefault(why, []).append(ticker)
        if why == "ticker":
            counts["excluded_ticker"] += 1
            continue
        if ok:
            counts["admitted_" + why] += 1
        else:
            counts["rank_only_" + why] += 1          # ranked in the RS pool, never listed (ruling (a), 2026-10-29)
        if ticker in unapplied:
            counts["split_unapplied"] += 1
            continue
        rc = float(bars.c[D])
        if D + 1 < cb.DOLLAR_VOL_WINDOW:
            counts["short_history"] += 1
            continue
        dv20 = cb._dollar_vol_median(bars, D)
        if not (rc >= bv.MIN_PRICE and dv20 >= bv.MIN_DOLLAR_VOL):
            counts["below_floors"] += 1
            continue
        r21, r63, r126 = bv.rs_returns_contiguous(bars, D, cidx)
        if r63 is None:
            counts["no_r63"] += 1
            continue
        members.append({"ticker": ticker, "security_type": st or "", "r21": r21, "r63": r63, "r126": r126,
                        "listable": bool(ok), "history": bv.history_ok(D, cidx), "bars": bars, "cidx": cidx})
    return {"members": members, "counts": counts, "fund_kept": fund_kept, "fund_excluded": fund_excl}


def night_cross_section(members: list, groups: Optional[list] = None) -> tuple:
    """The night's cross-section over the WHOLE RS pool -> (rs_best per member, {ticker: the pick model's four
    cross-section inputs}, the count of industry groups with 10+ members; the dict is None when the pick model's percentile step raised).
    `members` carry ticker / r21 / r63 / r126;
    `groups` = each member's SIC 2-digit group or None (default: no groups). rs_best is `cb.cross_section_one_date`'s,
    exactly as before 2026-11-14 — it is the best of the three return percentiles and never reads the groups. The
    pick model's inputs (01_build.py::work): rs_1m / rs_3m / rs_6m = `cb.percentile_ranks` of the 21 / 63 / 126-session
    return over the pool (0-100), group_strength = the percentile of the group's median 63-session return among the
    night's groups (None with no group, or a group under 10 members)."""
    groups = list(groups) if groups is not None else [None] * len(members)
    r21, r63, r126 = ([m[k] for m in members] for k in ("r21", "r63", "r126"))
    try:
        rs_best, _, grp, n_groups = cb.cross_section_one_date(r21, r63, r126, groups)
    except Exception as e:  # loud-ok: the industry-group step feeds ONLY the pick model (review 2026-11-14): redo the
        # cross-section without groups for rs_best (the gates), and give the pick model no inputs tonight (`xs` None ->
        # the order score orders the night, said in the audit row) — a group failure must not stop the list
        logger.error(f"breakout_v1_list: the cross-section with industry groups failed (no pick score tonight): "
                     f"{type(e).__name__}: {e}")
        rs_best, _, _, n_groups = cb.cross_section_one_date(r21, r63, r126, [None] * len(members))
        return rs_best, None, n_groups
    try:
        p21, p63, p126 = (cb.percentile_ranks(list(r)) for r in (r21, r63, r126))
        xs = {m["ticker"]: {"rs_1m": p21[j], "rs_3m": p63[j], "rs_6m": p126[j], "group_strength": grp[j]}
              for j, m in enumerate(members)}
    except Exception as e:  # loud-ok: the pick model's inputs only — rs_best (the gates) is already computed; rank_all then
        # gets no inputs (`xs` None -> the job disables the pick inputs), scores no name, falls back to the order score and
        # says so in the audit row. Never an empty dict: the four cross-section ranks would read the neutral 0.5 on
        # every name and the pick model would order the night without its strength inputs, silently.
        logger.error(f"breakout_v1_list: the pick model's cross-section failed (no pick score tonight): {type(e).__name__}: {e}")
        xs = None
    return rs_best, xs, n_groups


def _pick_inputs_for(ticker: str, g: dict, oi: dict, pick: dict, bars=None) -> dict:
    """One name's 16 raw pick-model inputs: the gate values + `oi`, the night's cross-section (`pick["xs"]`) and the
    52-week facts from the LONG bars (`pick["long"]`). A name the long series was built WITHOUT (one NULL / non-finite
    bar 201-300 sessions back drops the whole ticker in `build_series`; an unapplied split in that older window) reads
    its facts off its own `bars` — the 200-session series the gates just read — and is named in
    `pick["short_fallback"]` (review 2026-11-14: it used to get no score and rank last, silently). That is
    `base_facts`' own rule for a name with under 252 bars: the window is what exists. With no `pick["long"]` at all,
    or no `bars` passed, a name without long bars has no facts -> no score."""
    facts = None
    long = pick.get("long")
    lb = (long or {}).get(ticker)
    if lb is None and long is not None and bars is not None:
        lb = bars
        pick.setdefault("short_fallback", []).append(ticker)
    if lb is not None:
        try:
            facts = pm.base_facts(lb.h, lb.l, lb.c, len(lb) - 1)
        except Exception as e:  # one name's odd long bars cost that name its score, never the night
            logger.warning(f"breakout_v1_list: pick-model base facts {ticker} failed: {type(e).__name__}: {e}")
    return pm.pick_inputs(g, oi, facts=facts, xs=(pick.get("xs") or {}).get(ticker))


def evaluate_members(members: list, rs_best: list, today: date, removed: Optional[dict] = None,
                     pick: Optional[dict] = None) -> tuple:
    """`v1_gates` per member (with its rs_best) -> (passing list rows unranked, per-gate fail Counter, n evaluated).
    `removed` (optional, filled in place): {context gate: [tickers]} — the names that pass every OTHER gate and are
    taken off by one of the three context checks (2026-11-14), i.e. the names those checks removed from the list.
    `pick` (optional; None = no pick-model inputs, the rows as before 2026-11-14): {"xs": {ticker: the night's
    cross-section values}, "long": {ticker: the LONG DailyBars}, "extra": []}. Each passing row then carries
    `pick_inputs` (also inside `gates`) and `dollar_vol20`; `pick["extra"]` collects (in place) the pick inputs of the
    names ONLY a context check removed — they are never listed, but they belong to the population the pick model's
    within-night ranks were fitted on (`breakout_v1_pick_model.py`, "the list")."""
    rows, fails, n_eval = [], Counter(), 0
    for m, rb in zip(members, rs_best):
        if not m.get("listable", True):
            continue                                 # in the RS pool only (an ETF, a leveraged fund ...): never listed
        if not m["history"]:
            fails["history"] += 1
            continue
        bars, cidx = m["bars"], m["cidx"]
        D = len(bars) - 1
        try:
            g = bv.v1_gates(bars, D, rs_best=rb, cidx=cidx)
        except Exception as e:  # one name's odd bars must not blank the night; counted + logged
            fails["gate_error"] += 1
            logger.warning(f"breakout_v1_list: gates {m['ticker']} failed: {type(e).__name__}: {e}")
            continue
        n_eval += 1
        for k in g["failed"]:
            fails[k] += 1
        context_only = bool(g["failed"]) and set(g["failed"]) <= set(bv.CONTEXT_GATES)
        if removed is not None and context_only:
            for k in g["failed"]:
                removed.setdefault(k, []).append(m["ticker"])
        if pick is not None and not pick.get("disabled") and context_only:            # off the list, but inside the pick model's rank population
            try:
                pick.setdefault("extra", []).append(
                    _pick_inputs_for(m["ticker"], g, bv.order_inputs(bars, D, g["adr20"]), pick, bars))
            except Exception as e:
                logger.warning(f"breakout_v1_list: pick inputs {m['ticker']} failed: {type(e).__name__}: {e}")
        if not g["ok"]:
            continue
        oi = bv.order_inputs(bars, D, g["adr20"])        # the two order-score inputs, bars <= D (passing names only)
        gates = {k: v for k, v in g.items() if k != "pole_idx"}
        gates["order_inputs"] = oi
        row = {"scan_date": today, "ticker": m["ticker"], "level": float(g["level"]),
               "vol_bar": float(g["vol_bar"]), "adr20": g["adr20"], "rs_best": float(rb), "close": g["close"],
               "security_type": m["security_type"], "runup6m_adr": oi["runup6m_adr"],
               "spread10_adr": oi["spread10_adr"]}
        if pick is not None:
            try:
                # `pick["disabled"]` (the night's cross-section failed): no inputs, so no pick score for anyone
                pin = {} if pick.get("disabled") else _pick_inputs_for(m["ticker"], g, oi, pick, bars)
            except Exception as e:  # the name stays on the list; it has no pick score and ranks last under the model
                logger.warning(f"breakout_v1_list: pick inputs {m['ticker']} failed: {type(e).__name__}: {e}")
                pin = {}
            gates["pick_inputs"] = pin
            row["pick_inputs"] = pin
            # the dollar-volume backup reads the `universe` gate's own value, NEVER the pick inputs: a pick-model
            # failure (this name's, or the whole night's) must not blank a ranking that needs none of its code
            row["dollar_vol20"] = bv._f((((g.get("gates") or {}).get("universe") or {}).get("value") or {}).get("dollar_vol20"))
        row["gates"] = _json_safe(gates)
        rows.append(row)
    return rows, fails, n_eval


def pct_rank(values: list, *, ascending: bool = True) -> list:
    """pandas `Series.rank(pct=True)` (method 'average') over the non-None values: rank 1..n (tied values share the
    mean of their positions) / n, where n = the count of non-None values; None stays None. `ascending=False` gives
    the LARGEST value rank 1, so its pct is 1/n and the smallest value's is 1.0 — the research's
    `rank(pct=True, ascending=False)` (33_rank_topn.py)."""
    idx = [i for i, x in enumerate(values) if x is not None]
    n = len(idx)
    out: list = [None] * len(values)
    if not n:
        return out
    order = sorted(idx, key=lambda i: values[i], reverse=not ascending)
    k = 0
    while k < n:
        j = k
        while j + 1 < n and values[order[j + 1]] == values[order[k]]:
            j += 1
        avg = float(sum(range(k + 1, j + 2))) / (j - k + 1)        # the 1-based positions k+1..j+1, averaged
        for t in range(k, j + 1):
            out[order[t]] = avg / n
        k = j + 1
    return out


def rank_rows(rows: list) -> list:
    """The night's ORDER (spec §2, `33_rank_topn.py`), in place over the night's WHOLE passing list; returns it ranked.
    p_run = the within-night percentile of `runup6m_adr` (bigger first), p_tight = of `spread10_adr` (tighter first),
    order_score = (p_run + p_tight) / 2; list_rank 1 = the highest score, ties by ticker (the research's
    method='first' on ticker-sorted rows). A row missing an input has no score and ranks after every scored row (by
    ticker). The score ORDERS the list; it never removes a name (his spec: as a cut it would lose most of
    Qullamaggie's buys). It is comparable only inside one night."""
    p_run = pct_rank([r.get("runup6m_adr") for r in rows], ascending=True)
    p_tight = pct_rank([r.get("spread10_adr") for r in rows], ascending=False)
    for r, a, b in zip(rows, p_run, p_tight):
        r["order_score"] = (a + b) / 2 if (a is not None and b is not None) else None
    rows.sort(key=lambda r: (r["order_score"] is None, -(r["order_score"] or 0.0), r["ticker"]))
    for k, r in enumerate(rows, 1):
        r["list_rank"] = k
    return rows


def pick_scores(inputs: list) -> list:
    """The pick model's score per name over ONE night's rank population. `inputs` = each name's raw inputs
    (`pm.pick_inputs`) for the WHOLE population the ranks are taken in (tonight's passing names + the names only a
    context check removed). Each of the 15 ranked features becomes its `pct_rank` inside `inputs`; a blank
    cross-section rank reads 0.5 and a blank bar-derived input leaves the name unscored (`pm.HALF_FILL`). -> one score
    (log-odds; higher = more like a Qullamaggie buy) or None per name. Comparable only inside one night."""
    ranks = {f: pct_rank([x.get(f) for x in inputs]) for f in pm.PCT_FEATURES}
    out = []
    for i, x in enumerate(inputs):
        feats = {f: ranks[f][i] for f in pm.PCT_FEATURES}
        for f in pm.RAW_FEATURES:
            feats[f] = x.get(f)
        out.append(pm.score_from_features(feats))
    return out


def _rank_desc(rows: list, col: str) -> dict:
    """{ticker: 1-based rank} by `col`, the highest first, ties by ticker, a missing value after every scored name —
    those ordered by the ORDER SCORE (then ticker), so a night where only some names score never degrades to A-Z
    (review 2026-11-14); for the order score itself that is `rank_rows`' rule unchanged."""
    def key(r):
        v = r.get(col)
        if v is not None:
            return (False, -v, 0.0, r["ticker"])
        o = r.get("order_score")
        return (True, 0.0, -(o if o is not None else float("-inf")), r["ticker"])
    order = sorted(rows, key=key)
    return {r["ticker"]: k for k, r in enumerate(order, 1)}


def rank_all(rows: list, extra_inputs: Optional[list] = None, ranking: str = DEFAULT_RANKING) -> dict:
    """ALL THREE rankings on the night's passing list, in place; `ranking` (one of `RANKINGS`) sets `list_rank`.
      order_score    `rank_rows`, unchanged (the two within-night percentiles over the passing list)
      pick_score     `pick_scores` over the passing rows' `pick_inputs` + `extra_inputs` (the context-removed names)
      dollar_vol20   the 20-session median dollar volume (the `universe` gate's value), bigger first
    Every row gets the three scores, `rank_order_score` / `rank_pick_model` / `rank_dollar_volume`, `ranked_by` and
    `list_rank` (= the selected ranking's rank); the rows end sorted by `list_rank`. A missing score ranks last, ties
    by ticker, under every ranking. FALLBACK: if the selected ranking scored NO name on a non-empty list (a broken
    input, never a normal night) the order score sets `list_rank` instead and the summary says so — the list never
    silently degrades to alphabetical. Returns the summary for the audit row."""
    if ranking not in RANKINGS:
        raise ValueError(f"rank_all: unknown ranking {ranking!r}")
    rank_rows(rows)                                               # order_score, exactly as before 2026-11-14
    pick_error = None
    try:
        scores = pick_scores([r.get("pick_inputs") or {} for r in rows] + list(extra_inputs or []))
    except Exception as e:  # loud-ok: the order score and dollar volume need none of the pick model's code — the list is
        # still ranked and written (the FALLBACK below), and the audit row names the cause
        pick_error = f"{type(e).__name__}: {e}"
        logger.error(f"breakout_v1_list: the pick model raised (no pick score tonight): {pick_error}", exc_info=True)
        scores = [None] * len(rows)
    for r, s in zip(rows, scores):
        r["pick_score"] = s
        r["grade"] = grade_for(s)
        r.setdefault("dollar_vol20", (r.get("pick_inputs") or {}).get("dollar_vol20"))
    for k in RANKINGS:
        rk = _rank_desc(rows, RANKING_SCORE_COL[k])
        for r in rows:
            r[RANKING_RANK_COL[k]] = rk[r["ticker"]]
    scored = {k: sum(1 for r in rows if r.get(RANKING_SCORE_COL[k]) is not None) for k in RANKINGS}
    used, fallback = ranking, None
    if rows and not scored[ranking]:
        used, fallback = RANKING_ORDER_SCORE, f"{ranking} scored no name; the order score set the order"
        logger.error(f"breakout_v1_list: ranking {ranking!r} scored 0 of {len(rows)} names - falling back to the order score")
    for r in rows:
        r["list_rank"] = r[RANKING_RANK_COL[used]]
        r["ranked_by"] = used
    rows.sort(key=lambda r: r["list_rank"])

    def rnd(x):
        return None if x is None else round(float(x), AUDIT_SCORE_DP)
    return {"selected": ranking, "ranked_by": used, "fallback": fallback, "pick_error": pick_error, "scored": scored,
            "listed_n": len(rows),
            "grades": {**{g: sum(1 for r in rows if r.get("grade") == g) for g in GRADE_ORDER},
                       "none": sum(1 for r in rows if r.get("grade") is None)},
            "population_n": len(rows) + len(extra_inputs or []), "context_removed_in_population": len(extra_inputs or []),
            "top10": {k: [r["ticker"] for r in sorted(rows, key=lambda r: r[RANKING_RANK_COL[k]])[:MESSAGE_TOP_N]]
                      for k in RANKINGS},
            # the three scores of the first AUDIT_SCORES_MAX names by list_rank: [order, pick model, dollar volume ($, whole)]
            # — a copy for reading the night at a glance; the full record is the list table's own columns
            "scores": {r["ticker"]: [rnd(r.get("order_score")), rnd(r.get("pick_score")),
                                     None if r.get("dollar_vol20") is None else int(round(float(r["dollar_vol20"])))]
                       for r in rows[:AUDIT_SCORES_MAX]},
            "scores_omitted": max(0, len(rows) - AUDIT_SCORES_MAX)}


def fit_audit_detail(pub: dict, budget: Optional[int] = None) -> dict:
    """The run summary, made to FIT `mi_audit_log`'s detail budget so the row stays queryable JSON (past the budget
    `db` wraps the payload as a `_head` STRING and `detail->'ranking'` is gone; review 2026-11-14: the whole row read
    29.8k of 32k on a 1,353-name night). Shed in order, each marked in `audit_shed`, only while over: the per-name
    copy of the scores (`ranking.scores`; `scores_omitted` then counts every name), then the night's ticker list.
    Both are copies — the list table carries every name with all three scores and ranks. Returns `pub` (in place)."""
    if budget is None:
        from agents.market_intelligence.db import _AUDIT_DETAIL_MAX
        budget = _AUDIT_DETAIL_MAX - AUDIT_HEADROOM
    if len(json.dumps(pub)) <= budget:
        return pub
    shed = pub.setdefault("audit_shed", [])
    rk = pub.get("ranking") or {}
    if rk.get("scores"):
        rk["scores_omitted"] = int(rk.get("scores_omitted") or 0) + len(rk["scores"])
        rk["scores"] = {}
        shed.append("ranking.scores")
    if len(json.dumps(pub)) > budget and pub.get("tickers"):
        pub["tickers_omitted"] = len(pub["tickers"])
        pub["tickers"] = []
        shed.append("tickers")
    if len(json.dumps(pub)) > budget:
        logger.error(f"breakout_v1_list: the audit detail is still {len(json.dumps(pub))} chars after shedding {shed}")
    return pub


async def get_ranking() -> tuple:
    """Which ranking sets `list_rank` tonight -> (ranking, source, note). ONE source: the
    `mi_safeguard_state('breakout_v1_ranking', 'global')` row's state; no row = the pick model (source "default").
    There is NO env fallback (review 2026-11-14: a second source the acting-rules view could not see). A failed read
    is retried `RANKING_READ_TRIES` times — a row that says `order_score` must not become the pick model for a night
    on one transient miss; if every try fails, or the state is unknown, the pick model orders the night, the reason is
    NOTED (the audit row carries it) and logged at ERROR. Nothing here can stop the list. The literal name is passed
    so `scripts/live_rules.py` sees the switch. Flip (no deploy; acts from the next list write) — SQL in
    docs/setups/consolidation_breakout.md, 2026-11-14."""
    err = None
    for attempt in range(RANKING_READ_TRIES):
        try:
            row = await get_safeguard_state("breakout_v1_ranking", "global", timeout=RANKING_READ_TIMEOUT_S)
        except Exception as e:  # loud-ok: an order switch for a paper list — retried, then the default, noted in the audit row
            err = e
            logger.warning(f"breakout_v1_list: {RANKING_SWITCH} read failed (try {attempt + 1}/{RANKING_READ_TRIES}): {e}")
            if attempt + 1 < RANKING_READ_TRIES:
                await asyncio.sleep(RANKING_READ_PAUSE_S)
            continue
        state = str(row["state"]).strip().lower() if row is not None and row["state"] is not None else ""
        if state in RANKINGS:
            return state, "db", None
        if state:
            logger.error(f"breakout_v1_list: {RANKING_SWITCH} row carries unknown state {state!r} - the pick model orders tonight")
            return DEFAULT_RANKING, "default", f"unknown switch state {state!r}"
        return DEFAULT_RANKING, "default", None
    logger.error(f"breakout_v1_list: {RANKING_SWITCH} unreadable after {RANKING_READ_TRIES} tries - the pick model "
                 f"orders tonight whatever the row says: {err}")
    return DEFAULT_RANKING, "default", f"switch read failed {RANKING_READ_TRIES}x: {type(err).__name__}"


def _score_str(x) -> str:
    return "-" if x is None else f"{float(x):.2f}"


def _shown_score(r: dict) -> str:
    """The message's SCORE cell: the score of the ranking that set this row's `list_rank` (dollar volume in $M)."""
    by = r.get("ranked_by") or RANKING_ORDER_SCORE
    v = r.get(RANKING_SCORE_COL.get(by, "order_score"))
    if by == RANKING_DOLLAR_VOLUME:
        return "-" if v is None else f"{float(v) / 1e6:.0f}M"
    return _score_str(v)


def format_list_message(today: date, rows: list) -> Optional[str]:
    """The ONE Telegram message for a night's list, paper-prefixed (the paper chat); None for an empty list. Shows the
    TOP `MESSAGE_TOP_N` by list rank (`rows` ranked by `rank_all` / `rank_rows`; the header names the ranking that
    set it — the pick model, the order score or dollar volume) and the night's total count — the rebuilt
    list holds ~250 names a night, so the full list lives in `mi_breakout_v1_list`, never in the chat. It no longer
    names `/bgrade` (his word 2026-11-05: grades come from chart sheets shown in chat, not Telegram; #717 stage 2) —
    the command itself stays, as the catch-up path."""
    if not rows:
        return None
    from agents.market_intelligence.constants import mode_prefix
    shown = sorted(rows, key=lambda r: r.get("list_rank") or 10 ** 9)[:MESSAGE_TOP_N]
    lines = [f"{'#':>3s} {'TICKER':6s} {'LEVEL':>10s} {'SCORE':>6s} {'GR':>2s} {'RS':>5s}"]
    for r in shown:
        lines.append(f"{r.get('list_rank') or 0:>3d} {r['ticker']:6s} {r['level']:>10.2f} "
                     f"{_shown_score(r):>6s} {r.get('grade') or '-':>2s} {r['rs_best']:>5.1f}")
    n = len(rows)
    label = RANKING_LABEL.get(shown[0].get("ranked_by"), RANKING_LABEL[RANKING_ORDER_SCORE])
    more = f"\n…and {n - len(shown)} more (mi_breakout_v1_list)" if n > len(shown) else ""
    return (f"{mode_prefix('paper')}*Breakout v1 — watch list for the next session* ({today.isoformat()}, "
            f"{n} name{'s' if n != 1 else ''}; the top {len(shown)} by {label})\n"
            f"A name breaks out when it trades above its level. No order is placed from this message.\n"
            "```\n" + "\n".join(lines) + "\n```" + more)


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# The job
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def ranking_alert_message(today: date, rk: Optional[dict]) -> Optional[str]:
    """His word 2026-11-14 ("yes" to: a night the pick model fails and the order score takes over should page): one
    plain message when the selected ranking did not order the list, or ran without part of its inputs. None on a
    normal night. Sent whether or not breakout paper is on. Review 2026-11-15 added three more degraded nights to
    the SAME message: the industry-code read failed (`sic_error`: group strength blank for every name), the ranking
    switch could not be read or held an unknown value (`note`: the pick model ordered the night whatever the row
    says), and PARTIAL pick scoring (the pick model scored fewer than half the listed names)."""
    if not rk:
        return None
    why = []
    if rk.get("fallback"):
        why.append(f"the {RANKING_LABEL.get(rk.get('selected'), rk.get('selected'))} scored no stock, so the "
                   f"{RANKING_LABEL[RANKING_ORDER_SCORE]} ordered tonight's list")
    for k, what in (("pick_error", "the pick model raised"), ("xs_error", "its strength inputs failed"),
                    ("long_error", "its 1-year price history failed to load (it ran on 200 days)"),
                    ("sic_error", "the industry-code read failed (group strength is blank for every name tonight)"),
                    ("note", f"the ranking switch ({RANKING_SWITCH}) could not be used, so "
                             f"{RANKING_LABEL[DEFAULT_RANKING]} ordered tonight's list whatever the switch says")):
        if rk.get(k):
            why.append(f"{what}: {str(rk[k])[:160]}")
    listed = int(rk.get("listed_n") or 0)
    picked = (rk.get("scored") or {}).get(RANKING_PICK_MODEL)
    # a full fallback (the pick model selected and scoring nobody) is already the first line: not said twice
    if listed and picked is not None and 2 * int(picked) < listed and not rk.get("fallback"):
        why.append(f"the pick model scored only {int(picked)} of {listed} listed names (fewer than half); the rest "
                   f"follow the {RANKING_LABEL[RANKING_ORDER_SCORE]} behind the scored ones")
    if not why:
        return None
    from agents.market_intelligence.constants import mode_prefix
    return (f"{mode_prefix('paper')}*Breakout v1 — the list ranking degraded* ({today.isoformat()})\n- "
            + "\n- ".join(why) + "\nThe list was still written. Details: the breakout_v1_list_run audit row.")


def _new_out(today: date) -> dict:
    return {"date": today.isoformat(), "skipped": None, "timed_out": False, "error": None,
            "prefilter_tickers": 0, "bad_bars": 0, "universe_n": 0, "listable_n": 0, "evaluated": 0, "passing": 0, "written": 0,
            "counts": {}, "gate_fails": {}, "context_removed_n": {}, "context_removed": {}, "funds_kept": 0, "funds_excluded": 0, "funds_excluded_no_name": 0,
            "fund_kept_tickers": [], "fund_excluded_tickers": {}, "ranking": {}, "message": "not_needed", "wall_s": 0.0}


async def _run(today: date, out: dict) -> list:
    cal = await cb_get_calendar(today, CALENDAR_SESSIONS)
    if not cal or cal[-1] != today:
        out["skipped"] = "no_spy_bar_for_today"
        return []
    cal_index = {d: i for i, d in enumerate(cal)}
    n = len(cal)
    start = cal[max(0, n - HISTORY_SESSIONS)]
    long_start = cal[max(0, n - max(HISTORY_SESSIONS, pm.HISTORY_SESSIONS))]
    liq_start = cal[max(0, n - cb.DOLLAR_VOL_WINDOW)]
    # ONE read from `long_start` (the pick model's 52-week facts need 252 bars); every path that existed before
    # 2026-11-14 — the pool, the gates, the order score — still sees exactly the `start`-bounded rows it always did.
    long_rows = await cb_get_universe_bars(today, long_start, liq_start, min_price=bv.MIN_PRICE,
                                           prefilter_dollar_vol=PREFILTER_DOLLAR_VOL)
    rows = [r for r in long_rows if r[1] >= start]
    tickers = sorted({r[0] for r in rows})
    out["prefilter_tickers"] = len(tickers)
    types = await bv1_get_security_types_named(tickers)
    unapplied = {s["ticker"] for s in await get_unapplied_splits(start, upto=today)}
    series, sstats = await asyncio.to_thread(build_series, rows, cal_index)
    # The pick model's LONG series, isolated (review 2026-11-14): the list, the order score and dollar volume need
    # none of it, so a failure here costs the night its 52-week look-back (every name then reads its facts off the
    # 200-session bars, counted in `ranking.short_bar_facts_n`), never the list.
    long_error = None
    try:
        long_unapplied = (unapplied if long_start == start
                          else {s["ticker"] for s in await get_unapplied_splits(long_start, upto=today)})
        long_series, _ = await asyncio.to_thread(build_series, long_rows, cal_index)
    except Exception as e:  # loud-ok: named in the audit row (`ranking.long_error`) and logged at ERROR
        long_unapplied, long_series, long_error = set(), {}, f"{type(e).__name__}: {e}"
        logger.error(f"breakout_v1_list: the pick model's long bar series failed (52-week facts off the short bars "
                     f"tonight): {long_error}", exc_info=True)
    del rows, long_rows
    out["bad_bars"] = sstats.get("bad_bars", 0)
    today_ci = cal_index[today]

    members, counts, fund_kept, fund_excl = [], Counter(), [], {}
    items = list(series.items())
    for lo in range(0, len(items), SCAN_CHUNK):
        part = await asyncio.to_thread(scan_members, dict(items[lo:lo + SCAN_CHUNK]), today_ci=today_ci,
                                       types=types, unapplied=unapplied)
        members.extend(part["members"])
        counts.update(part["counts"])
        fund_kept.extend(part["fund_kept"])
        for k, v in part["fund_excluded"].items():
            fund_excl.setdefault(k, []).extend(v)
    out["counts"] = dict(counts)
    out["universe_n"] = len(members)                 # the RS pool (every type at the floors)
    out["listable_n"] = sum(1 for m in members if m["listable"])
    out["funds_kept"] = len(fund_kept)
    out["funds_excluded"] = sum(len(v) for v in fund_excl.values())
    out["funds_excluded_no_name"] = len(fund_excl.get("fund_no_name", []))
    out["fund_kept_tickers"] = sorted(fund_kept)[:FUND_EXCLUDED_LIST_MAX]
    out["fund_excluded_tickers"] = {k: sorted(v)[:FUND_EXCLUDED_LIST_MAX] for k, v in fund_excl.items()}

    # the pool's industry groups (SIC 2-digit, the shadow's cache `mi_consolidation_breakout_sic`) for the pick model's
    # group strength; a name with no cached code has no group and its group rank reads 0.5 (the research's fill)
    sic_error = None
    try:
        sic = await cb_get_sic([m["ticker"] for m in members])
    except Exception as e:  # loud-ok: the group strength is one of 16 inputs; the night's list must still be written
        sic, sic_error = {}, f"{type(e).__name__}: {e}"
        logger.warning(f"breakout_v1_list: industry-code read failed (group strength blank tonight): {sic_error}")
    groups = [(sic.get(m["ticker"]) or {}).get("sic2") or cb.sic2((sic.get(m["ticker"]) or {}).get("sic_code"))
              for m in members]
    rs_best, xs, n_groups = night_cross_section(members, groups)
    xs_error = None if xs is not None else "the cross-section percentiles raised (see the log)"
    pick = {"xs": xs or {}, "long": {t: b for t, (b, _c) in long_series.items() if t not in long_unapplied},
            "extra": [], "disabled": xs is None}
    del long_series
    ranking, ranking_source, ranking_note = await get_ranking()
    list_rows, fails, n_eval, removed = [], Counter(), 0, {}
    for lo in range(0, len(members), SCAN_CHUNK):
        r_, f_, e_ = await asyncio.to_thread(evaluate_members, members[lo:lo + SCAN_CHUNK],
                                             rs_best[lo:lo + SCAN_CHUNK], today, removed, pick)
        list_rows.extend(r_)
        fails.update(f_)
        n_eval += e_
    short_fb = sorted(set(pick.get("short_fallback") or []))
    out["ranking"] = rank_all(list_rows, pick["extra"], ranking)
    out["ranking"].update(source=ranking_source, note=ranking_note, switch=RANKING_SWITCH, sic_error=sic_error,
                          pool_with_industry_code=sum(1 for g_ in groups if g_ is not None), industry_groups=n_groups,
                          listed_with_group_strength=sum(1 for r in list_rows
                                                         if (r.get("pick_inputs") or {}).get("group_strength") is not None),
                          listed_with_52w_facts=sum(1 for r in list_rows
                                                    if (r.get("pick_inputs") or {}).get("dist_52w") is not None),
                          # names whose 52-week facts were read off the 200-session bars (no usable long series: a
                          # bad bar or an unapplied split 201-300 sessions back, or `long_error`); listed + context-removed
                          long_error=long_error, xs_error=xs_error, short_bar_facts_n=len(short_fb),
                          short_bar_facts=short_fb[:SHORT_FALLBACK_LIST_MAX],
                          model=pm.PROVENANCE)
    out["evaluated"], out["passing"], out["gate_fails"] = n_eval, len(list_rows), dict(fails)
    out["context_removed_n"] = {k: len(v) for k, v in removed.items()}
    out["context_removed"] = {k: sorted(v)[:CONTEXT_REMOVED_LIST_MAX] for k, v in removed.items()}
    if fails.get("gate_error", 0) and n_eval == 0:
        # every name's gates raised (e.g. a numpy change under the 2026-11-14 context checks): an empty list must not
        # look like a quiet night — raise, so audit_wrap's notify_job_failure pages after the audit row (review 11-14)
        raise RuntimeError(f"breakout_v1_list: gates raised on every name ({fails['gate_error']}); nothing evaluated")
    out["written"] = await bv1_replace_list(today, list_rows)
    out["tickers"] = [r["ticker"] for r in list_rows]
    return list_rows


async def run_breakout_v1_list(today: Optional[date] = None) -> dict:
    """The nightly job body (17:55 ET mon-fri). Returns the run summary (also the audit row's detail)."""
    if today is None:
        from agents.market_intelligence.collector import et_today
        today = et_today()
    out = _new_out(today)
    t0 = time.monotonic()
    first_exc: Optional[BaseException] = None
    rows: list = []
    try:
        rows = await asyncio.wait_for(_run(today, out), timeout=BUDGET_S)
    except asyncio.TimeoutError:
        out["timed_out"] = True
        logger.error(f"breakout_v1_list: exceeded its {BUDGET_S}s budget - fail-open; the next night rebuilds its list")
        await log_audit_event(AUDIT_ERROR_EVENT, f"{today}: exceeded its {BUDGET_S}s budget (fail-open; no list written)",
                              json.dumps({"budget_s": BUDGET_S, "universe_n": out["universe_n"]}))
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
        logger.error(f"breakout_v1_list: failed: {e}", exc_info=True)
        first_exc = e

    alert = ranking_alert_message(today, out.get("ranking")) if (rows and first_exc is None) else None
    if alert:
        try:
            from agents.market_intelligence.briefing import send_telegram_message
            out["ranking_alert"] = "sent" if await send_telegram_message(alert) else "send_failed"
        except Exception as e:  # loud-ok: recorded on the audit row; the list is already written
            out["ranking_alert"] = f"send_failed: {type(e).__name__}"
            logger.warning(f"breakout_v1_list: the ranking alert for {today} raised: {type(e).__name__}: {e}")
    msg = format_list_message(today, rows) if (rows and not out["timed_out"] and first_exc is None) else None
    # His word 2026-11-10 ("I don't want to see these garbage charts again", after the first paper session bought
    # charts with no higher lows and no surfing average): the message goes out ONLY while breakout paper is on.
    # The list itself is still computed and written every night (the rebuild scores against it).
    if msg and not await get_runtime_toggle(BREAKOUT_V1_PAPER_TOGGLE, BREAKOUT_V1_PAPER_TOGGLE_ENV):
        out["message"] = "suppressed_paper_off"
        msg = None
    if msg:
        try:
            from agents.market_intelligence.briefing import send_telegram_message
            sent = await send_telegram_message(msg)
            out["message"] = "sent" if sent else "send_failed"
            if not sent:
                logger.warning(f"breakout_v1_list: the list message for {today} was not delivered "
                               f"(send_telegram_message returned False; {len(rows)} name(s) are in the table)")
        except Exception as e:
            out["message"] = "send_failed"
            logger.warning(f"breakout_v1_list: the list message for {today} raised: {type(e).__name__}: {e}")
    out["wall_s"] = round(time.monotonic() - t0, 1)
    pub = fit_audit_detail(_json_safe(out))
    if out["skipped"]:
        summary = f"{today}: skipped - {out['skipped']}"
    else:
        summary = (f"{today}: {out['passing']} name(s) on the list of {out['universe_n']} universe name(s) "
                   f"({out['evaluated']} evaluated); funds kept {out['funds_kept']}, excluded {out['funds_excluded']} "
                   f"({out['funds_excluded_no_name']} with no stored name); message {out['message']}; {out['wall_s']}s"
                   + (f"; TIMED OUT" if out["timed_out"] else "")
                   + (f"; ERROR: {out['error']}" if out["error"] else ""))
    try:
        await log_audit_event(AUDIT_RUN_EVENT, summary, json.dumps(pub))
    except Exception as ex:  # loud-ok: log_audit_event self-catches; logger fires here, the rows are already durable
        logger.warning(f"breakout_v1_list audit emit failed (non-fatal): {ex}")
    if first_exc is not None:
        raise first_exc
    return pub


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# /bgrade — his grade on a list name (a LABEL, never a gate). The handler is agent.py::_handle_bgrade_command.
# ═══════════════════════════════════════════════════════════════════════════════════════════════
GRADES = {"a+": "A+", "a": "A", "b": "B", "c": "C", "skip": "skip"}
UNGRADED_NIGHTS = 5
BGRADE_USAGE = ("Usage: `/bgrade TICKER A+|A|B|C|skip [note]`\n"
                "Grades a name on the breakout v1 list (the latest night that listed it). "
                "A grade is a label — it never blocks or places anything.\n"
                "Bare `/bgrade` shows the top 10 ungraded names by list rank (newest list night first) "
                "and how many of the last 5 list nights' names are ungraded.")


def parse_bgrade(text: str) -> Optional[dict]:
    """`/bgrade` -> {"list": True}; `/bgrade TICKER GRADE [note...]` -> {"list": False, ticker, grade, note};
    anything else (no grade, an unknown grade, a malformed ticker) -> None (the caller replies with the usage)."""
    toks = (text or "").strip().split()
    if toks and toks[0].startswith("/"):
        toks = toks[1:]
    if not toks:
        return {"list": True}
    ticker = toks[0].upper().lstrip("$")
    if not cb.UNIVERSE_TICKER_RE.fullmatch(ticker) or len(toks) < 2:
        return None
    grade = GRADES.get(toks[1].lower())
    if grade is None:
        return None
    note = " ".join(toks[2:]).strip() or None
    return {"list": False, "ticker": ticker, "grade": grade, "note": note}


def format_ungraded(rows: list) -> str:
    """The bare `/bgrade` reply. `rows` = every ungraded list name of the last 5 list nights, newest night first and
    by list_rank inside a night (`db.bv1_ungraded`). At ~250 names a night that is ~1,250 rows, so the reply shows
    the TOP `MESSAGE_TOP_N`: the newest night's best-scored ungraded names (spilling to the night before when the
    newest has fewer than 10 left) plus the total ungraded count and the count per night. SCORE is the score of the
    ranking that set that night's order (`ranked_by`; the order score on rows written before 2026-11-14). A score
    compares names only within one night, so the newest night is read first."""
    if not rows:
        return f"_No ungraded breakout v1 names in the last {UNGRADED_NIGHTS} list nights._"

    def _d(r):
        return r["scan_date"].isoformat() if hasattr(r["scan_date"], "isoformat") else str(r["scan_date"])
    per_night: dict = {}
    for r in rows:
        per_night[_d(r)] = per_night.get(_d(r), 0) + 1
    shown = rows[:MESSAGE_TOP_N]
    lines = [f"{'NIGHT':10s} {'#':>3s} {'TICKER':6s} {'LEVEL':>10s} {'SCORE':>6s} {'RS':>5s}"]
    for r in shown:
        lines.append(f"{_d(r):10s} {int(r.get('list_rank') or 0):>3d} {r['ticker']:6s} {float(r['level']):>10.2f} "
                     f"{_shown_score(r):>6s} {float(r['rs_best']):>5.1f}")
    n = len(rows)
    nights = ", ".join(f"{d} {k}" for d, k in sorted(per_night.items(), reverse=True))
    return (f"*Breakout v1 — {n} ungraded name{'s' if n != 1 else ''}* (last {UNGRADED_NIGHTS} list nights: "
            f"{nights}); the top {len(shown)} by list rank:\n```\n" + "\n".join(lines) + "\n```\n"
            "`/bgrade TICKER A+|A|B|C|skip [note]`")
