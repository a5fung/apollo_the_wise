"""Breakout v1 — the PICK MODEL (the list's live ORDER since 2026-11-14). PURE: numpy only, no DB, no I/O.

OPERATOR-SIGNED 2026-11-14: "pick model, let's continue to eval and keep all the old models we have as backup".

WHAT IT IS. An L2 logistic (lambda 1.0) fitted ONCE on Qullamaggie's buys of 2017-2020 and FROZEN here — never refit
by this code. Its score orders the night's list (highest first); it never removes a name.
  fit         scripts/probes/_717_pick_model_1113/02_fit_test.py `fit` (62,051 breakout rows on days his positions
              panel covers, 410 of them a buy of his within 2 sessions) -> scripts/probes/_717_pick_model_1113/coef.json,
              model "primary"; registration docs/analysis/cb_pick_model_2026-11-13.md
  features    built by scripts/probes/_717_pick_model_1113/01_build.py (the raw values) and 02_fit_test.py::load (the
              transform): 15 of the 16 are the name's 0..1 RANK INSIDE THE NIGHT'S LIST (pandas rank(pct=True),
              ties share the mean rank), a blank value reading 0.5; `first_base` is a plain 0/1. There are NO
              standardisation constants — the within-night rank is the whole transform.
  the list    the rank is taken inside the night's list BEFORE the three context checks of 2026-11-14 (the model was
              fitted and tested on that population: `_717_rank2_1114/01_rank2.py`, "features = percentile inside the
              night's 4% list, as fitted; NO refit, no re-percentiling"). The live job therefore ranks over tonight's
              passing names PLUS the names only a context check took off, and scores the passing names.
  test        scripts/probes/_717_rank2_1114/01_rank2.out: 2021-01..2022-03, Qullamaggie buys in the day's top 5 —
              the order score 19, this model 41, dollar volume 47.

`tests/test_breakout_v1_pick_model.py` pins the constants below against coef.json and the live score against the
research's per-row score on whole era-A nights rebuilt from bars. Owner doc: docs/setups/consolidation_breakout.md.
"""
from __future__ import annotations

import math
from typing import Optional

import numpy as np

from agents.market_intelligence import breakout_v1 as bv

PROVENANCE = {
    "coef_file": "scripts/probes/_717_pick_model_1113/coef.json",
    "model": "primary",
    "registration": "docs/analysis/cb_pick_model_2026-11-13.md",
    "fit_window": "2017-01..2020-12 (breakout day E)",
    "fit_rows": 62051,
    "fit_positives": 410,
    "l2_lambda": 1.0,
    "frozen": "2026-11-14",
}
# registration order — the order of coef.json's "features"
FEATURES = ("rs_1m", "rs_3m", "rs_6m", "prior_move", "runup6m", "depth_adr", "base_len", "spread10_adr", "adr20",
            "dollar_vol20", "dist_52w", "dist_level", "vs_ema21_adr", "since_low", "first_base", "group_strength")
INTERCEPT = -11.112141998212907
COEF = (0.30504878436382216, 0.560499390441737, 1.2551405202175137, 0.2646302936868828, 0.809098005107688,
        0.3100920128131061, -0.27635406756490083, -0.8804675770676802, 1.2485709331233772, 5.298813214505164,
        -0.8098154553021355, 0.14771511211666427, -0.07014010403449009, 1.2388319045039278, 0.3650954494291876,
        -0.14801666494938892)
RAW_FEATURES = ("first_base",)                       # used as its 0/1 value; every other feature is a within-night rank
PCT_FEATURES = tuple(f for f in FEATURES if f not in RAW_FEATURES)
# The research fills a blank rank with 0.5 (`rank(pct=True).fillna(0.5)`). In its capture only two inputs were ever
# blank: the 6-month strength rank (2.4% of list rows — under 126 consecutive sessions) and the group strength (35.8% —
# no industry code, or a group under 10 members). Those cross-section inputs keep the research's 0.5. Every other input
# comes from the name's own bars and was never blank in the research: a name missing one gets NO score and ranks last.
HALF_FILL = frozenset({"rs_1m", "rs_3m", "rs_6m", "group_strength"})
YEAR = 252                                           # the 52-week window, in the name's own bars (01_build.py YEAR)
HISTORY_SESSIONS = 300                               # sessions the list job loads for `base_facts` (252 + hole margin)


def base_facts(h, l, c, D: int) -> Optional[tuple]:
    """`01_build.py::base_facts`, bars <= D: (close(D) / the highest high of the last 252 bars, bars since the lowest
    low of those 252, the count of COMPLETED earlier bases since that low). A base = a stretch of at least
    `bv.BASE_MIN` bars between two consecutive "new high since the major low" days. With fewer than 252 bars the
    window is what exists (the research's rule). None when the window holds no finite positive high."""
    a = max(0, D - YEAR + 1)
    hw, lw = np.asarray(h[a:D + 1], dtype=float), np.asarray(l[a:D + 1], dtype=float)
    if not hw.size or not np.isfinite(lw).any() or not np.isfinite(hw).any():
        return None
    top = float(np.nanmax(hw))
    if not (top > 0) or not math.isfinite(float(c[D])):
        return None
    k = int(np.nanargmin(lw))
    hh = hw[k:]
    cm = np.maximum.accumulate(hh)
    idx = np.flatnonzero(np.r_[True, hh[1:] > cm[:-1]])          # "new high since the major low" days
    return float(c[D] / top), int(len(lw) - 1 - k), int((np.diff(idx) >= bv.BASE_MIN).sum())


def pick_inputs(g: dict, oi: dict, *, facts: Optional[tuple], xs: Optional[dict]) -> dict:
    """One name's 16 RAW model inputs at D (a value that cannot be computed is None).
    `g` = `bv.v1_gates`' result (every non-context gate evaluated), `oi` = `bv.order_inputs`, `facts` =
    `base_facts` on the LONG bars (None = not available), `xs` = the night's cross-section for the name:
    {"rs_1m", "rs_3m", "rs_6m": `cb.percentile_ranks` of the 21/63/126-session return over the RS pool,
     "group_strength": `cb.cross_section_one_date`'s group percentile on the SIC 2-digit group}."""
    gg = g.get("gates") or {}
    xs = xs or {}

    def val(gate, key):
        v = (gg.get(gate) or {}).get("value") or {}
        return v.get(key)
    level, close, adr = g.get("level"), g.get("close"), g.get("adr20")
    dist_level = None
    if level is not None and close is not None and adr is not None and close > 0 and adr > 0:
        dist_level = bv._f((float(level) / float(close) - 1) / float(adr))
    d52, since_low, bases_before = facts if facts is not None else (None, None, None)
    return {"rs_1m": xs.get("rs_1m"), "rs_3m": xs.get("rs_3m"), "rs_6m": xs.get("rs_6m"),
            "prior_move": bv._f(g.get("prior_move")), "runup6m": bv._f(oi.get("runup6m")),
            "depth_adr": bv._f(val("base_depth", "depth_adr")), "base_len": val("prior_move", "base_len"),
            "spread10_adr": bv._f(oi.get("spread10_adr")), "adr20": bv._f(adr),
            "dollar_vol20": bv._f(val("universe", "dollar_vol20")), "dist_52w": bv._f(d52), "dist_level": dist_level,
            "vs_ema21_adr": bv._f(val("ema21", "vs_ema21_adr")), "since_low": since_low,
            "first_base": None if bases_before is None else (1.0 if bases_before == 0 else 0.0),
            "group_strength": xs.get("group_strength")}


def score_from_features(f: dict) -> Optional[float]:
    """intercept + sum(coef x feature) over the 16 TRANSFORMED features `f` (ranks 0..1, first_base 0/1). A feature
    that is None gives None — except the `HALF_FILL` ranks, which read 0.5 (the research's fill)."""
    s = INTERCEPT
    for name, coef in zip(FEATURES, COEF):
        v = f.get(name)
        if v is None and name in HALF_FILL:
            v = 0.5
        if v is None:
            return None
        s += coef * float(v)
    return s
