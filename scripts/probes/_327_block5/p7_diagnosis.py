"""Block 5 / P7 — WHY the delayed-entry lane loses: the diagnosis. $0, read-only, offline.

PRE-REGISTRATION OF RECORD (committed before any Q1-Q4 number is computed; nothing below
changes after). The operator, 2026-09-26: "We should have a good cohort already, unsure
collecting more will change, we need to understand what the issue is." Block 5 and its two
follow-ups (`327_exit_determination_2026-09-26.md`, `327_leaders_ep_management_2026-09-26.md`)
proved no stop x target x exit, no leader filter and no EP-style management pays on ~3,400
fires. This probe does not test another rule. It asks four descriptive questions of the same
fires and ranks what it finds by how much of the loss each explains.

──────────────────────────────────────────────────────────────────────────────────────────
POPULATION AND ITS FIRST CUT — established during ORIENTATION, before this registration,
and therefore DECLARED here rather than discovered later.
──────────────────────────────────────────────────────────────────────────────────────────
Population = every fire in the Block 5 extract with >= 10 sessions elapsed by 2026-09-25
(P2's `sessions_elapsed` >= 10 from `p2_fire_walks.csv`; n = 3,398), never settlement status.

The fired campaigns are classified by what OUR OWN EP SCREEN did on the gap day:
  EP-ALERT  the (ticker, ep_date) is a row of `mi_ep_alerts` with COALESCE(source,'live')='live'
            — the seed query's own LIVE_SOURCE_SQL — at any tier (HIGH / MODERATE / 'none').
  NOT-EP    everything else, split by the furthest stage the scan log shows for that
            (ticker, gap day): universe_floor (prev close < $5 MIN_PREV_CLOSE, or prior-day
            volume < 50,000 MIN_PREV_DAY_VOLUME) · gap_floor · rvol / pre-market volume ·
            quality_filter · extension · cooldown · scored-below-the-bar · post-grade filter
            (routine catalyst, M&A) · no scan row. `reject_stage` where stamped, else the
            `filter_reason` prefix (the older rows carry no stage column).
Seen before registration and disclosed: 22 of 941 fired campaigns are alerts (100 fires, 51
with >= 10 sessions elapsed); 855 campaigns (3,460 fires, 92%) were rejected at the universe
floor, 783 of them for a prior close under $5; the six 08-24..08-31 alerts (CHRN, CRWD, DG,
OKTA, SOLS, VEEV) reproduce the seed query's docstring ("1,269 campaigns, SIX were EP alerts").
Also seen: 1,457 of the 3,075 settled stops in the population fell on the fire session itself.
No other Q1-Q4 number was computed before this file was committed. EVERY table below carries
the two cohorts side by side (EP-ALERT n is small and is reported as small, never pooled away).

──────────────────────────────────────────────────────────────────────────────────────────
THE OUTCOME MEASURE — the lane's own arm, on the sessions-elapsed population
──────────────────────────────────────────────────────────────────────────────────────────
R10 = the incumbent stop + the lane's trail arm (a close below max(SMA10, SMA20)) read at
session 10: -1.00R on a stop (house convention; P3 measured gap-charging at 0.03R on this
cell and it is NOT applied here), the exit close's R on a trail exit, else the session-10
close marked to market. R10_none (no exit) beside it. Sources, in this order:
  (1) production's recorded settlement (`outcome`, `stop_hit_date`, `r_trail_s10`,
      `r_none_s10`, `mfe_r`, `mae_r`) for settled rows — production walked them with the real
      minute bars at settle time; these ARE the lane's own arm;
  (2) the 259 rows still open at the extract (outcome NULL, >= 10 sessions elapsed): the
      probe walks the same arm from the daily table with the real `sma_trail_line` (closes
      before the fire from `daily_closes(_warmup).csv`, day 0 per P2's `day0_bars_for_fire`
      — real post-fire 5-min bars, else the cached day-0 excursion, else the daily fold for a
      level fire); a row whose day 0 cannot be ordered ABSTAINS and is counted, never scored;
  (3) `outcome='unscoreable'` rows (degenerate geometry) are counted, never scored.
Every fire-time price is rescaled to the daily table's scale by P2's `scale_factor` (the
post-fire split rows); entry_price is reported UNSCALED for the price buckets (the price he
would have paid).
ANCHORS, printed before any table is read:
  (a) the probe's own walk on settled rows with a resolvable day 0 must reproduce
      `stop_hit_date` and `r_trail_s10` (match rate; the P1/P2 number is ~99.8%);
  (b) the R10 mean on the ids P3 walked for its incumbent trail cell (`p3_events.csv`,
      convention=recorded, stop=incumbent, target=none) is printed beside P3's verified
      -0.29R (n = 1,320); a difference over 0.02R is stated before any other number is read.

──────────────────────────────────────────────────────────────────────────────────────────
Q1 — HOW TRADES FAIL (the path). Per pattern, both cohorts.
──────────────────────────────────────────────────────────────────────────────────────────
Path classes at session 10, declared:
  STOP-D0     stopped on the fire session. At daily grade the order of "went green" vs
              "hit the stop" is UNKNOWN; where a post-fire minute source exists (real
              `mi_intraday_bars`, else the row's cached `day0_post_high`) the class is split
              into green-first / straight-down; otherwise "order unknown". Never folded into
              NEVER-GREEN.
  NEVER-GREEN stopped at session >= 1 with NO high above the entry strictly before the stop
              session. Day-0 credit: a level (daily-grade) fire's fire-day high counts (price
              passed the level on the way there — the `reached_4r` rule); a minute fire's
              post-fire bars count where a source exists; its day-0 DAILY high is never
              credited.
  GREEN-THEN-STOPPED  stopped at session >= 1 with a high above the entry before the stop
              session; sub-bucketed by the peak strictly before the stop session:
              (0, 1R] · (1R, 2R] · (2R, 3R] · > 3R.
  OPEN-AT-S10 not stopped by session 10: trail-exited (R at the exit close) or still marked
              at the session-10 close; split positive / negative.
Sessions to stop: 0 · 1 · 2 · 3-5 · 6-10 · not by s10. Peak before the stop reported TWICE:
strict (strictly before the stop session, from daily highs) and recorded `mfe_r` (the stop
session's own high folds in — the same-session ordering caveat, stated wherever it is used).
Loss contribution = the summed R10 of each class over the total summed R10 (a negative
number), per pattern and pooled, both cohorts.

──────────────────────────────────────────────────────────────────────────────────────────
Q2 — THE ENTRY MOMENT: fire vs the matched same-window non-fire control (P2's method).
──────────────────────────────────────────────────────────────────────────────────────────
Rows = P2's own walks (`p2_fire_walks.csv`, `p2_control_walks.csv`): +2xADR$ before -1xADR$
at s10, PESSIMISTIC bound. The control of a pattern = every non-fire session (any-pattern
`is_fire_session` False) of the campaigns where that pattern fired, entered at that session's
close (P2's `matched_controls`). PRIMARY like-for-like read = the fire entered at the fire
session's CLOSE (`close_pess_s10`) against the control's close entry — same convention on
both sides, so the level-priced head start P2 found cannot leak in; the recorded entry
(`pess_s10`) is reported beside it. Pre-entry features, on the daily table's scale, in ADR$
(P2's campaign ADR$), t = the entry session, identical for fires and controls:
  drift3         (close[t-1] - close[t-4]) / ADR         the prior three sessions' net move
  drift1         (close[t-1] - close[t-2]) / ADR
  bounce         (entry - min low over [t-3, t]) / ADR   the rise off the recent low into the
                                                          entry, the entry session's own low
                                                          included (the dead-cat measure)
  intraday       (entry - open[t]) / ADR                 the entry session's own move to the
                                                          entry (close - open for a control)
  overhead       (max high over [EP day, t-1] - entry) / ADR   distance UP to the campaign's
                                                          running high (overhead supply);
                                                          negative = above every prior high
  dist_gap_high  (EP-day high - entry) / ADR
  pos_ep_close   (entry - EP-day close) / ADR
  pos_ep_low     (entry - EP-day low) / ADR
  prior_reclaims the number of sessions in (EP day, t) that already reclaimed the pattern's
                 own level (EP low for ep_low_reclaim; EP close for ep_close_reclaim and
                 ep_close_620_prox: a session with low <= level < close); for ep_high_break
                 the number of prior sessions whose high reached the EP-day high. Fires also
                 carry `reentry_shape` (first vs a re-entry shape).
  session_idx    sessions since the EP day.
Strata = terciles of each feature cut on the pattern's CONTROL distribution (declared, not
tuned); the 2-D stratum = bounce tercile x overhead tercile. Decomposition per pattern:
  gap = fire rate - control rate
      = [fire rate - control rate REWEIGHTED to the fires' stratum shares]   (within-stratum:
                                                   fires do worse at the same kind of moment)
      + [reweighted control rate - raw control rate]                        (composition:
                                                   fires sit at worse kinds of moment)
reported per feature and for the 2-D stratum with n per stratum; a stratum under 20 rows on
either side is pooled into its neighbour and said so. "Buying into overhead supply / a
dead-cat bounce" is answered by the sign and size of the composition term for `bounce` and
`overhead`, and by the fire-vs-control rate inside each tercile.

──────────────────────────────────────────────────────────────────────────────────────────
Q3 — WHICH STOCKS. Pre-entry buckets, declared now; per bucket n · mean R10 · stopped-by-s10
rate · kept >= 3R (R10 >= 3) · runner rate. Both cohorts.
──────────────────────────────────────────────────────────────────────────────────────────
  cohort            EP-ALERT vs NOT-EP, the latter by rejection stage
  price at the fire unscaled entry_price: < $1 · $1-5 · $5-20 · > $20
  EP tier at the gap  alert HIGH · alert MODERATE (incl. tier 'none' alerts) · scored below
                    the bar · rejected before scoring
  ep_score          terciles among scored fires (scan log max ep_score that day; alert score
                    where alerted)
  catalyst grade    scan-log `catalyst_quality`, else `llm_catalyst_quality`, among graded
  gap size          terciles of the watch table's `gap_pct`, cut on the fire population
  sessions since EP 1 · 2 · 3-5 · 6-10 · 11+
  run-up into the EP  the screen's own formula from daily bars: (prev close - MIN close over
                    [ep_date - 10 calendar days, ep_date)) / MIN close x 100 (ep_detector's
                    extension check); < 10% · 10-25% · 25-50% · >= 50% (the screen's cap)
  active theme      scan-log `in_active_theme` (alert row first); unknown reported as unknown
  market, fire day  SPY close-to-close on the fire date: up / down; the SPY 5-session return
                    sign beside it
  dollar volume     terciles of EP-day $ volume (watch `ep_dollar_volume`) and of fire-day
                    $ volume (day_volume x day_close), both
Runner labels: PRIMARY = P6's campaign definition (EP date <= 09-04, the highest high within
15 sessions of the EP >= +50% over the EP-day close — the definition behind the "9% of fires"
fact he holds; fires in later campaigns are outside the label's population and shown as such;
declared now: 0 of the 120 runner campaigns are alerts, so tier / score AUCs against this
label are degenerate by construction, not a null). SECONDARY = fire-anchored: the highest high
in sessions 1..10 after the fire >= +50% over the scaled entry — fully observed for the whole
population, and the one that says "this fire was in a stock that then ran".
AUC = Mann-Whitney with ties at 1/2, Hanley-McNeil 95% CI, n_pos / n_neg, of every numeric
pre-entry trait (price, gap %, ep_score, sessions since EP, run-up, EP-day and fire-day $
volume, adr20_pct, stop_width_pct, SPY return, and Q2's drift3 / bounce / overhead /
pos_ep_close / prior_reclaims) against each runner label, on the whole population and within
NOT-EP; a trait dark on more than half the rows is reported as DARK, not as a null.

──────────────────────────────────────────────────────────────────────────────────────────
Q4 — THE LINK TO THE EP ITSELF. Per fired campaign, from daily bars.
──────────────────────────────────────────────────────────────────────────────────────────
Sessions 1-3 after the EP day against the EP close and EP low:
  HELD    every close of sessions 1-3 >= the EP-day close
  FADED   a close below the EP close, none below the EP low
  FAILED  a close below the EP-day low within sessions 1-3
plus depth = (EP close - min low over sessions 1-3) / ADR and the day-1 close move in ADR.
TAUTOLOGY DECLARED: ep_low_reclaim fires only after an undercut of the EP low and the two
close-reclaim patterns only after a dip under the EP close, so "did the EP fail" is partly the
trigger's own precondition. The read is therefore HOW HARD and HOW EARLY, the fire's own
position at entry (entry < EP low · EP low <= entry < EP close · EP close <= entry <= EP
high · above the EP high), the share of re-entry shapes, and the same sessions-1-3 read on
runner vs non-runner campaigns (do the stocks that ran hold the EP close?).

──────────────────────────────────────────────────────────────────────────────────────────
RANKING THE CAUSES BY LOSS — method before numbers.
──────────────────────────────────────────────────────────────────────────────────────────
A mechanism's share = the summed R10 of the fires it labels over the total summed R10, within
the cohort. Overlapping labels (a same-session stop that is also a re-entry into a FAILED EP,
etc.) are shown in a JOINT table and never summed across causes. The population fact (which
cohort a fire is in) is the FRAME of the write-up, not a mechanism: a stock being rejected by
the screen does not make its fire lose.

THE LINE: nothing here picks a stop, target, exit, selection rule or population; no toggle,
table, deploy or PLAN.md line. Outputs: p7_summary.json (every table, committed),
p7_rows.csv / p7_q2_rows.csv (per-row features and labels, gitignored, regenerable).
Inputs: the P0/P3 pulls + extract_p7.sh (index_daily.csv, ep_scan_log.csv, ep_alerts.csv) +
p2_fire_walks.csv / p2_control_walks.csv + p3_events.csv + p6_summary.json.
"""
import csv
import json
import math
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from agents.market_intelligence.delayed_entry_shadow import (  # real code, never re-implemented
    sma_trail_line, _trading_days, to_rth_5min, day0_pseudo_bars,
)
from p1_probe import load_triggers, load_daily_closes, load_intraday_raw   # P1's loaders
from p2_probe import day0_bars_for_fire, scale_factor                       # P2's day-0 + scale rules

LAST_SESSION = date(2026, 9, 25)
PRIMARY_K = 10
WINDOW = 20
PATTERNS = ("ep_low_reclaim", "ep_close_reclaim", "ep_high_break", "ep_close_620_prox")
COHORTS = ("EP-ALERT", "NOT-EP")
MIN_PREV_CLOSE, MIN_PREV_DAY_VOLUME = 5.0, 50_000          # ep_detector.py constants, read today
RUNNER_EP_MAX, RUNNER_GAIN = date(2026, 9, 4), 1.5         # P6's campaign runner definition
STAGE_ORDER = ["universe_floor", "gap_floor", "rvol_gate", "quality_filter", "extension", "cooldown",
               "duplicate", "score_bar", "post_grade_filter"]


def _f(s):
    if s is None or s == "" or (isinstance(s, float) and math.isnan(s)):
        return None
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def _mean(v):
    v = [x for x in v if x is not None and not (isinstance(x, float) and math.isnan(x))]
    return round(float(np.mean(v)), 4) if v else None


def _med(v):
    v = [x for x in v if x is not None and not (isinstance(x, float) and math.isnan(x))]
    return round(float(np.median(v)), 4) if v else None


def _pct(a, b):
    return round(100.0 * a / b, 2) if b else None


def _q(v, qs=(0.25, 0.5, 0.75)):
    v = [x for x in v if x is not None and not (isinstance(x, float) and math.isnan(x))]
    return {f"p{int(q * 100)}": round(float(np.quantile(v, q)), 3) for q in qs} if v else {}


# ── loaders for the P7 pulls ──────────────────────────────────────────────────────────

def load_daily_full():
    """{ticker: sorted list of (date, o, h, l, c, vol)} + {ticker: {date: idx}} — warm-up + P0 pulls."""
    rows = defaultdict(dict)
    for fn in ("daily_closes_warmup.csv", "daily_closes.csv"):
        with open(HERE / fn, newline="") as fh:
            for r in csv.DictReader(fh):
                d = date.fromisoformat(r["trade_date"])
                rows[r["ticker"]][d] = (d, _f(r["open_price"]), _f(r["high_price"]), _f(r["low_price"]),
                                        _f(r["close"]), _f(r["volume"]))
    series, index = {}, {}
    for tk, m in rows.items():
        lst = [m[d] for d in sorted(m)]
        series[tk] = lst
        index[tk] = {b[0]: i for i, b in enumerate(lst)}
    return series, index


def load_index_daily():
    out = defaultdict(dict)
    with open(HERE / "index_daily.csv", newline="") as fh:
        for r in csv.DictReader(fh):
            out[r["ticker"]][date.fromisoformat(r["trade_date"])] = _f(r["close"])
    return out


def load_alerts():
    a = pd.read_csv(HERE / "ep_alerts.csv", keep_default_na=False, na_values=[""])
    a["source"] = a["source"].fillna("live")
    a = a[a["source"] == "live"].copy()                      # LIVE_SOURCE_SQL
    a["ep_date"] = a["alert_date"]
    return a


def load_scan_log():
    s = pd.read_csv(HERE / "ep_scan_log.csv", low_memory=False, keep_default_na=False, na_values=[""])

    def cls(row):
        st, fr = row.reject_stage, str(row.filter_reason)
        if pd.notna(row.ep_score):
            return "scored"
        if isinstance(st, str):
            return st
        if fr.startswith("filter:universe"):
            return "universe_floor"
        if fr.startswith("quality filter"):
            return "quality_filter"
        if fr.startswith("already up"):
            return "extension"
        if fr.startswith("score "):
            return "score_bar"
        if fr.startswith("already scored"):
            return "duplicate"
        if fr.startswith("EP cooldown"):
            return "cooldown"
        if fr.startswith("filter:pm_rvol") or fr.startswith("filter:session_rvol") or fr.startswith("pre-mkt volume"):
            return "rvol_gate"
        if fr.startswith("routine catalyst") or fr.startswith("M&A"):
            return "post_grade_filter"
        return "other"
    s["cls"] = s.apply(cls, axis=1)
    rk = {k: i for i, k in enumerate(STAGE_ORDER)}
    rk["other"] = -1
    rk["scored"] = 99
    s["rk"] = s["cls"].map(rk)
    s["univ_reason"] = np.where(s.filter_reason.astype(str).str.startswith("filter:universe_prev_close_too_low"), "prev_close_lt_5",
                        np.where(s.filter_reason.astype(str).str.startswith("filter:universe_prev_day_illiquid"), "prev_day_vol_lt_50k", ""))
    g = (s.sort_values("rk").groupby(["scan_date", "ticker"])
         .agg(furthest=("cls", "last"), max_score=("ep_score", "max"),
              catalyst=("catalyst_quality", lambda x: next((v for v in x.dropna()), None)),
              llm_catalyst=("llm_catalyst_quality", lambda x: next((v for v in x.dropna()), None)),
              in_theme=("in_active_theme", lambda x: next((v for v in x.dropna()), None)),
              ext_scan=("extension_pct", lambda x: next((v for v in x.dropna()), None)),
              univ_reason=("univ_reason", lambda x: next((v for v in x if v), "")))
         .reset_index().rename(columns={"scan_date": "ep_date"}))
    return g


# ── the walk for the still-open rows + the anchor ─────────────────────────────────────

def lane_arm_walk(entry, stop, d0_bars, sess_bars, closes_before, fire_close, k=PRIMARY_K):
    """The lane's own arm from bars on one scale (named so it is not mistaken for the live-stack
    `walk_arm`, whose callers `tests/test_exit_era_callers_name_their_strategy.py` gates). d0_bars: [(h,l)] post-fire (day 0);
    sess_bars: [(o,h,l,c)] sessions 1..k (None = hole). Returns dict with stop_idx (0 = day 0),
    trail_exit_idx, r_trail_k, r_none_k, peak_strict_r, or status abstain."""
    risk = entry - stop
    for h, l in d0_bars:
        if l <= stop:
            return {"stop_idx": 0, "r_trail": -1.0, "r_none": -1.0, "trail_exit_idx": None, "peak_strict": None}
    closes = [c for c in closes_before if c is not None] + [fire_close]
    trail_exit_idx, trail_r = None, None
    line = sma_trail_line(closes)
    if line is not None and fire_close < line:
        trail_exit_idx, trail_r = 0, (fire_close - entry) / risk
    highs_before = [h for h, l in d0_bars]
    for i, b in enumerate(sess_bars, start=1):
        if i > k:
            break
        if b is None:
            return {"status": "abstain", "reason": f"hole_s{i}"}
        o, h, l, c = b
        if l <= stop:
            peak = (max(highs_before) - entry) / risk if highs_before else None
            return {"stop_idx": i, "r_trail": -1.0 if trail_exit_idx is None else trail_r, "r_none": -1.0,
                    "trail_exit_idx": trail_exit_idx, "peak_strict": peak, "mark_at_stop_high": (h - entry) / risk}
        highs_before.append(h)
        closes.append(c)
        if trail_exit_idx is None:
            line = sma_trail_line(closes)
            if line is not None and c < line:
                trail_exit_idx, trail_r = i, (c - entry) / risk
        if i == k:
            r_mark = (c - entry) / risk
            return {"stop_idx": None, "r_trail": trail_r if trail_exit_idx is not None else r_mark,
                    "r_none": r_mark, "trail_exit_idx": trail_exit_idx,
                    "peak_strict": (max(highs_before) - entry) / risk if highs_before else None}
    return {"status": "abstain", "reason": "short_window"}


# ── AUC ───────────────────────────────────────────────────────────────────────────────

def auc_ci(pos, neg):
    pos = np.asarray([x for x in pos if x is not None and not np.isnan(x)], dtype=float)
    neg = np.asarray([x for x in neg if x is not None and not np.isnan(x)], dtype=float)
    n1, n0 = len(pos), len(neg)
    if n1 < 5 or n0 < 5:
        return {"auc": None, "n_pos": int(n1), "n_neg": int(n0)}
    ranks = pd.Series(np.concatenate([pos, neg])).rank(method="average").to_numpy()
    a = (ranks[:n1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)
    q1, q2 = a / (2 - a), 2 * a * a / (1 + a)
    se = math.sqrt((a * (1 - a) + (n1 - 1) * (q1 - a * a) + (n0 - 1) * (q2 - a * a)) / (n1 * n0))
    return {"auc": round(float(a), 3), "ci95": [round(float(a - 1.96 * se), 3), round(float(a + 1.96 * se), 3)],
            "n_pos": int(n1), "n_neg": int(n0)}


# ── bucket aggregation ────────────────────────────────────────────────────────────────

def agg(df):
    n = int(len(df))
    sc = df[df.r10.notna() & df.floored]
    out = {"n": n, "n_scored": int(len(sc)), "mean_r10": _mean(sc.r10.tolist()), "median_r10": _med(sc.r10.tolist()),
           "sum_r10": round(float(sc.r10.sum()), 2) if len(sc) else None,
           "stopped_by_s10_pct": _pct(int(sc.stopped_by_s10.sum()), len(sc)),
           "kept_ge3r_pct": _pct(int((sc.r10 >= 3 - 1e-9).sum()), len(sc)),
           "kept_ge3r_n": int((sc.r10 >= 3 - 1e-9).sum()),
           "runner_campaign_pct": _pct(int(df.runner_campaign.fillna(False).sum()), int(df.runner_label_pop.sum())) if "runner_label_pop" in df else None,
           "runner_campaign_n": int(df.runner_campaign.fillna(False).sum()),
           "runner_fire_pct": _pct(int(df.runner_fire.fillna(False).sum()), int(df.runner_fire.notna().sum())),
           "runner_fire_n": int(df.runner_fire.fillna(False).sum()),
           "names": int(df.ticker.nunique())}
    return out


def by_bucket(df, col, order=None):
    out = {}
    keys = order if order is not None else sorted(df[col].dropna().unique().tolist(), key=str)
    for k in keys:
        sub = df[df[col] == k]
        if len(sub):
            out[str(k)] = agg(sub)
    nd = df[df[col].isna()]
    if len(nd):
        out["unknown"] = agg(nd)
    return out


def terciles(series, labels=("T1_low", "T2_mid", "T3_high")):
    s = series.astype(float)
    if s.notna().sum() < 9:
        return pd.Series([None] * len(s), index=s.index, dtype=object)
    q1, q2 = s.quantile([1 / 3, 2 / 3]).tolist()
    return pd.Series(np.where(s.isna(), None, np.where(s <= q1, labels[0], np.where(s <= q2, labels[1], labels[2]))), index=s.index, dtype=object)


def main():
    triggers = load_triggers()
    daily = load_daily_closes()                     # P1 shape: {ticker: {date: {high_price, low_price, close}}}
    intraday_raw = load_intraday_raw()
    series, index = load_daily_full()
    idx_daily = load_index_daily()
    alerts = load_alerts()
    scan = load_scan_log()
    fw = pd.read_csv(HERE / "p2_fire_walks.csv", low_memory=False, keep_default_na=False, na_values=[""])
    cw = pd.read_csv(HERE / "p2_control_walks.csv", low_memory=False, keep_default_na=False, na_values=[""])
    watch = pd.read_csv(HERE / "watch.csv", low_memory=False, keep_default_na=False, na_values=[""])
    w0 = watch[watch.session_idx == 0][["ticker", "ep_date", "gap_pct", "prev_close", "ep_dollar_volume"]].copy()
    p6 = json.load(open(HERE / "p6_summary.json"))
    runner_camps = {tuple(k.split("|")) for k in p6["runners"]["detail"]}
    p3_ids = set()
    with open(HERE / "p3_events.csv", newline="") as fh:
        for r in csv.DictReader(fh):
            if r["convention"] == "recorded" and r["stop"] == "incumbent" and r["target"] == "none":
                p3_ids.add(int(r["id"]))
    summary = {"pulled": (HERE / "ep_scan_log.pulled_at").read_text().strip()}

    # ── cohorts per campaign ──
    T = pd.read_csv(HERE / "trigger.csv", low_memory=False, keep_default_na=False, na_values=[""])
    camps = T[["ticker", "ep_date"]].drop_duplicates()
    camps = camps.merge(alerts[["ticker", "ep_date", "score_tier", "ep_score", "catalyst_quality", "in_active_theme"]]
                        .rename(columns={"score_tier": "alert_tier", "ep_score": "alert_score",
                                         "catalyst_quality": "alert_catalyst", "in_active_theme": "alert_theme"}),
                        on=["ticker", "ep_date"], how="left")
    camps = camps.merge(scan, on=["ticker", "ep_date"], how="left")
    camps["cohort"] = np.where(camps.alert_tier.notna(), "EP-ALERT", "NOT-EP")
    camps["stage"] = np.where(camps.alert_tier.notna(), "alert_" + camps.alert_tier.fillna("").astype(str),
                              np.where(camps.furthest == "scored", "scored_below_bar", camps.furthest.fillna("no_scan_row")))
    camps["stage_detail"] = np.where(camps.stage == "universe_floor", "universe_floor:" + camps.univ_reason.fillna(""), camps.stage)
    camps["ep_tier"] = np.where(camps.alert_tier == "HIGH", "alert_HIGH",
                                np.where(camps.alert_tier.notna(), "alert_MODERATE_or_none",
                                         np.where(camps.furthest == "scored", "scored_below_bar", "rejected_before_scoring")))
    camps["ep_score_any"] = camps.alert_score.fillna(camps.max_score)
    camps["catalyst_any"] = camps.alert_catalyst.fillna(camps.catalyst).fillna(camps.llm_catalyst)
    camps["theme_any"] = camps.alert_theme
    camps.loc[camps.theme_any.isna(), "theme_any"] = camps.in_theme
    camps = camps.merge(w0, on=["ticker", "ep_date"], how="left")
    summary["cohorts"] = {"fired_campaigns": int(len(camps)), "by_cohort": camps.cohort.value_counts().to_dict(),
                          "by_stage": camps.stage_detail.value_counts().to_dict(),
                          "first_run_alerts_reproduced": sorted(camps[(camps.cohort == "EP-ALERT") & (camps.ep_date <= "2026-08-31")].ticker.tolist())}
    camp_map = camps.set_index(["ticker", "ep_date"]).to_dict("index")

    # ── per-fire rows ──
    fw_by_id = fw.set_index("id").to_dict("index")
    rows, anchor, open_walk = [], Counter(), Counter()
    for t in triggers:
        w = fw_by_id.get(int(t["id"]))
        if w is None or int(w["sessions_elapsed"]) < PRIMARY_K:
            continue
        tk, fd = t["ticker"], t["fire_date"]
        cm = camp_map[(tk, t["ep_date"].isoformat())]
        f = scale_factor(t, daily.get(tk, {}))
        entry, stop = (t["entry_price"] or 0) * f, (t["stop_price"] or 0) * f
        risk = entry - stop
        sessions = _trading_days(fd + timedelta(days=1), LAST_SESSION)[:WINDOW]
        ser, ix = series.get(tk, []), index.get(tk, {})
        i_fire = ix.get(fd)
        ep_bar = ser[ix[t["ep_date"]]] if t["ep_date"] in ix else None
        sess_bars = []
        for d in sessions[:PRIMARY_K]:
            j = ix.get(d)
            b = ser[j] if j is not None else None
            sess_bars.append((b[1], b[2], b[3], b[4]) if b and None not in (b[2], b[3], b[4]) else None)
        row = {"id": int(t["id"]), "ticker": tk, "ep_date": t["ep_date"].isoformat(), "fire_date": fd.isoformat(),
               "rung": t["rung"], "rshape": t["reentry_shape"], "resolution": t["resolution"],
               "sessions_since_ep": int(t["sessions_since_ep"]) if t["sessions_since_ep"] else None,
               "cohort": cm["cohort"], "stage": cm["stage_detail"], "ep_tier": cm["ep_tier"],
               "ep_score": cm["ep_score_any"], "catalyst": cm["catalyst_any"], "theme": cm["theme_any"],
               "gap_pct": cm["gap_pct"], "ep_dollar_volume": cm["ep_dollar_volume"],
               "entry_price": t["entry_price"], "stop_width_pct": _f(t["stop_width_pct"]), "adr20_pct": _f(t["adr20_pct"]),
               "scale": round(f, 4), "level_priced": t["fire_minute_et"] is None, "outcome": t["outcome"] or None,
               "mfe_rec": _f(t["mfe_r"]), "r_trail_s10_rec": _f(t["r_trail_s10"]), "r_none_s10_rec": _f(t["r_none_s10"]),
               "fire_dollar_volume": (_f(t["day_volume"]) or 0) * (t["day_close"] or 0) or None,
               "runner_campaign": ((tk, t["ep_date"].isoformat()) in runner_camps) if t["ep_date"] <= RUNNER_EP_MAX else None,
               "runner_label_pop": t["ep_date"] <= RUNNER_EP_MAX}
        # market on the fire day
        spy = idx_daily.get("SPY", {})
        sd = sorted(spy)
        if fd in spy:
            k = sd.index(fd)
            row["spy_ret_1d"] = round(100 * (spy[fd] / spy[sd[k - 1]] - 1), 3) if k >= 1 else None
            row["spy_ret_5d"] = round(100 * (spy[fd] / spy[sd[k - 5]] - 1), 3) if k >= 5 else None
        # run-up into the EP: the screen's own formula
        if ep_bar is not None and i_fire is not None:
            j_ep = ix[t["ep_date"]]
            prev = ser[j_ep - 1][4] if j_ep >= 1 else None
            win = [b[4] for b in ser[:j_ep] if b[0] >= t["ep_date"] - timedelta(days=10) and b[4]]
            row["runup_pct"] = round(100 * (prev - min(win)) / min(win), 2) if (prev and win and min(win) > 0) else None
            row["ep_close"], row["ep_low"], row["ep_high"] = ep_bar[4], ep_bar[3], ep_bar[2]
        if risk <= 0 or not entry:
            row.update({"path": "unscoreable", "r10": None, "stopped_by_s10": None})
            rows.append(row)
            continue
        # day-0 post-fire bars for the strict peak / the same-session split (incumbent stop)
        d0, d0_src = day0_bars_for_fire(t, f, stop, daily.get(tk, {}), intraday_raw)
        row["day0_source"] = d0_src
        # ── R10 and the stop index: production's settlement first ──
        stop_idx = None
        if t["outcome"] == "stop" and t.get("stop_hit_date"):
            shd = date.fromisoformat(t["stop_hit_date"])
            stop_idx = 0 if shd == fd else (sessions.index(shd) + 1 if shd in sessions else None)
        settled = t["outcome"] in ("stop", "time_exit")
        if settled:
            row["stop_idx"] = stop_idx
            row["stopped_by_s10"] = stop_idx is not None and stop_idx <= PRIMARY_K
            row["r10"] = _f(t["r_trail_s10"])
            row["r10_none"] = _f(t["r_none_s10"])
            row["src"] = "recorded"
        elif t["outcome"] == "unscoreable":
            row.update({"path": "unscoreable", "r10": None, "stopped_by_s10": None, "src": "unscoreable"})
            rows.append(row)
            continue
        else:
            if d0 is None:
                row.update({"path": "abstain_day0", "r10": None, "stopped_by_s10": None, "src": "abstain"})
                open_walk["abstain_day0"] += 1
                rows.append(row)
                continue
            closes_before = [ser[j][4] for j in range(max(0, i_fire - 25), i_fire)] if i_fire is not None else []
            fire_close = ser[i_fire][4] if i_fire is not None else None
            wr = lane_arm_walk(entry, stop, d0, sess_bars, closes_before, fire_close)
            if wr.get("status") == "abstain":
                row.update({"path": "abstain_hole", "r10": None, "stopped_by_s10": None, "src": "abstain"})
                open_walk[wr["reason"]] += 1
                rows.append(row)
                continue
            stop_idx = wr["stop_idx"]
            open_walk["stop_found_on_open_row" if stop_idx is not None else "open_ok"] += 1
            row["stop_idx"] = stop_idx
            row["stopped_by_s10"] = stop_idx is not None
            row["r10"], row["r10_none"], row["src"] = round(wr["r_trail"], 4), round(wr["r_none"], 4), "walked_open"
        # ── the strict peak before the stop session (day-0 credit rule) ──
        d0_credit = None
        if t["fire_minute_et"] is None:
            fb = ser[i_fire] if i_fire is not None else None
            d0_credit = fb[2] if fb else None                       # a level fire's own day high
        elif d0:
            d0_credit = max(h for h, l in d0)                       # post-fire bars from a source
        highs = []
        if d0_credit is not None:
            highs.append(d0_credit)
        last = (stop_idx if stop_idx is not None else PRIMARY_K + 1)
        for i, b in enumerate(sess_bars, start=1):
            if i >= last:
                break
            if b is not None:
                highs.append(b[1])
        if stop_idx == 0:
            # a same-session stop: the order inside the session is unknown at daily grade; only a
            # minute source can say what printed BEFORE the stop bar
            pre = []
            if d0 and t["fire_minute_et"] is not None:
                for h, l in d0:
                    if l <= stop:
                        break
                    pre.append(h)
            row["peak_strict"] = round((max(pre) - entry) / risk, 4) if pre else None
        else:
            row["peak_strict"] = round((max(highs) - entry) / risk, 4) if highs else None
        if stop_idx is not None and 1 <= stop_idx <= PRIMARY_K and sess_bars[stop_idx - 1] is not None:
            row["stop_session_high_r"] = round((sess_bars[stop_idx - 1][1] - entry) / risk, 4)
        # anchor (a): our walk vs the recorded settlement on settled rows with a resolvable day 0
        if settled and d0 is not None and i_fire is not None:
            closes_before = [ser[j][4] for j in range(max(0, i_fire - 25), i_fire)]
            wr = lane_arm_walk(entry, stop, d0, sess_bars, closes_before, ser[i_fire][4])
            if wr.get("status") == "abstain":
                anchor["abstain"] += 1
            else:
                s_ok = (wr["stop_idx"] == (stop_idx if (stop_idx is not None and stop_idx <= PRIMARY_K) else None))
                r_ok = row["r10"] is not None and abs(wr["r_trail"] - row["r10"]) <= 0.02
                anchor["stop_match" if s_ok else "stop_mismatch"] += 1
                anchor["r_match" if r_ok else "r_mismatch"] += 1
        # path class
        if stop_idx is not None and stop_idx <= PRIMARY_K:
            if stop_idx == 0:
                if d0 and t["fire_minute_et"] is not None:
                    green = False
                    for h, l in d0:
                        if l <= stop:
                            break
                        if h > entry:
                            green = True
                    row["path"] = "STOP-D0_green_first" if green else "STOP-D0_straight_down"
                else:
                    row["path"] = "STOP-D0_order_unknown"
            elif row["peak_strict"] is None:
                # stopped at session >= 1 with NO observable bar before the stop session (a minute
                # fire with no day-0 source, stopped on session 1): the order is unknown, as on day 0
                row["path"] = "STOP-S1_no_day0_source_order_unknown"
            elif row["peak_strict"] <= 0:
                ssh = row.get("stop_session_high_r")
                row["path"] = "NEVER-GREEN_stop_session_high_above_entry" if (ssh is not None and ssh > 0) else "NEVER-GREEN_never_above_entry"
            else:
                pk = row["peak_strict"]
                row["path"] = ("GREEN_0-1R" if pk <= 1 else "GREEN_1-2R" if pk <= 2 else "GREEN_2-3R" if pk <= 3 else "GREEN_gt3R")
        else:
            row["path"] = "OPEN-AT-S10_pos" if (row["r10"] or 0) > 0 else "OPEN-AT-S10_neg"
        # ADDED AFTER Q1 WAS READ (declared in the doc): what the stock did AFTER an early stop —
        # separates "the stop sat inside the noise" from "the stock kept falling". Read on every
        # fire: the session-10 close and the sessions-1..10 high, both against the entry, in R.
        c10 = sess_bars[PRIMARY_K - 1][3] if len(sess_bars) >= PRIMARY_K and sess_bars[PRIMARY_K - 1] is not None else None
        row["s10_close_r"] = round((c10 - entry) / risk, 4) if c10 is not None else None
        hs_all = [b[1] for b in sess_bars if b is not None]
        row["s1_10_high_r"] = round((max(hs_all) - entry) / risk, 4) if hs_all else None
        # fire-anchored runner: highest high in sessions 1..10 >= +50% over the scaled entry
        hs = [b[1] for b in sess_bars if b is not None]
        row["runner_fire"] = (max(hs) >= RUNNER_GAIN * entry) if hs else None
        row["max_up_10s_pct"] = round(100 * (max(hs) / entry - 1), 1) if hs else None
        rows.append(row)
    R = pd.DataFrame(rows)
    summary["population"] = {"n": int(len(R)), "by_src": R.src.value_counts(dropna=False).astype(int).to_dict(),
                             "by_cohort": R.cohort.value_counts().to_dict(), "open_walk": dict(open_walk),
                             "path_unscored": R[R.r10.isna()].path.value_counts().to_dict()}
    summary["anchor_a_walk_vs_recorded"] = dict(anchor)
    p3sub = R[R.id.isin(p3_ids) & R.r10.notna() & (R.stop_width_pct >= 0.5)]
    summary["anchor_b_vs_p3_cell"] = {"p3_cell": {"n": 1320, "mean_r": -0.2904, "tail3_pct": 2.58},
                                      "this_read_on_p3_ids": {"n": int(len(p3sub)), "mean_r10": _mean(p3sub.r10.tolist()),
                                                              "kept_ge3r_pct": _pct(int((p3sub.r10 >= 3 - 1e-9).sum()), len(p3sub))}}
    print("anchor (a) walk vs recorded:", dict(anchor))
    print("anchor (b) vs P3 cell (n=1320, -0.2904):", summary["anchor_b_vs_p3_cell"]["this_read_on_p3_ids"])
    print("population:", summary["population"])

    # ── Q1 ──
    PATH_ORDER = ["STOP-D0_straight_down", "STOP-D0_green_first", "STOP-D0_order_unknown",
                  "STOP-S1_no_day0_source_order_unknown",
                  "NEVER-GREEN_never_above_entry", "NEVER-GREEN_stop_session_high_above_entry",
                  "GREEN_0-1R", "GREEN_1-2R", "GREEN_2-3R", "GREEN_gt3R", "OPEN-AT-S10_neg", "OPEN-AT-S10_pos"]
    R["floored"] = R.stop_width_pct >= 0.5
    summary["width_floor"] = {"rule": "stop_width_pct >= 0.5 (Block 5's rule; the anchor cell is read on it)",
                              "n_scored_unfloored": int(R.r10.notna().sum()), "sum_r10_unfloored": round(float(R[R.r10.notna()].r10.sum()), 2),
                              "n_scored_floored": int((R.r10.notna() & R.floored).sum()), "sum_r10_floored": round(float(R[R.r10.notna() & R.floored].r10.sum()), 2),
                              "dropped_by_floor": int((R.r10.notna() & ~R.floored).sum()),
                              "max_r10_unfloored": round(float(R.r10.max()), 2), "max_r10_floored": round(float(R[R.floored].r10.max()), 2)}
    S = R[R.r10.notna() & R.floored].copy()
    S["stop_bucket"] = pd.cut(S.stop_idx.fillna(99), [-1, 0, 1, 2, 5, 10, 200], labels=["s0", "s1", "s2", "s3-5", "s6-10", "not_by_s10"]).astype(str)
    q1 = {}
    for coh in ("ALL",) + COHORTS:
        for pat in ("ALL",) + PATTERNS:
            sub = S if coh == "ALL" else S[S.cohort == coh]
            sub = sub if pat == "ALL" else sub[sub.rung == pat]
            if not len(sub):
                continue
            tot = float(sub.r10.sum())
            cell = {"n": int(len(sub)), "sum_r10": round(tot, 2), "mean_r10": _mean(sub.r10.tolist()),
                    "stopped_by_s10_pct": _pct(int(sub.stopped_by_s10.sum()), len(sub)),
                    "kept_ge3r_pct": _pct(int((sub.r10 >= 3 - 1e-9).sum()), len(sub)),
                    "paths": {}, "sessions_to_stop": {}}
            for pth in PATH_ORDER:
                ps = sub[sub.path == pth]
                if len(ps):
                    cell["paths"][pth] = {"n": int(len(ps)), "share_of_fires_pct": _pct(len(ps), len(sub)),
                                         "sum_r10": round(float(ps.r10.sum()), 2),
                                         "share_of_total_r10_pct": _pct(float(ps.r10.sum()), tot) if tot else None,
                                         "mean_r10": _mean(ps.r10.tolist()),
                                         "peak_strict": _q(ps.peak_strict.tolist()), "mfe_recorded": _q(ps.mfe_rec.tolist())}
            for sb in ["s0", "s1", "s2", "s3-5", "s6-10", "not_by_s10"]:
                bs = sub[sub.stop_bucket == sb]
                if len(bs):
                    cell["sessions_to_stop"][sb] = {"n": int(len(bs)), "pct": _pct(len(bs), len(sub)),
                                                    "sum_r10": round(float(bs.r10.sum()), 2)}
            st = sub[sub.stopped_by_s10 == True]
            cell["stopped_rows"] = {"n": int(len(st)), "peak_strict_gt0_pct": _pct(int((st.peak_strict > 0).sum()), int(st.peak_strict.notna().sum())),
                                    "peak_strict_ge1r_pct": _pct(int((st.peak_strict >= 1).sum()), int(st.peak_strict.notna().sum())),
                                    "mfe_rec_ge1r_pct": _pct(int((st.mfe_rec >= 1).sum()), int(st.mfe_rec.notna().sum())),
                                    "mfe_rec_ge3r_pct": _pct(int((st.mfe_rec >= 3).sum()), int(st.mfe_rec.notna().sum())),
                                    "peak_strict_n": int(st.peak_strict.notna().sum())}
            q1[f"{coh}|{pat}"] = cell
    # ADDED AFTER Q1 WAS READ (declared in the doc): after an early stop, did the stock recover?
    after = {}
    for coh in ("ALL",) + COHORTS:
        sub = S if coh == "ALL" else S[S.cohort == coh]
        for name, m in (("stopped_s0", sub.stop_idx == 0), ("stopped_s1_s2", (sub.stop_idx >= 1) & (sub.stop_idx <= 2)),
                        ("stopped_s3_s10", (sub.stop_idx >= 3) & (sub.stop_idx <= 10)), ("not_stopped_by_s10", sub.stop_idx.isna())):
            x = sub[m & sub.s10_close_r.notna()]
            if len(x):
                after[f"{coh}|{name}"] = {"n": int(len(x)),
                    "s10_close_above_entry_pct": _pct(int((x.s10_close_r > 0).sum()), len(x)),
                    "s10_close_below_stop_pct": _pct(int((x.s10_close_r <= -1).sum()), len(x)),
                    "s10_close_r": _q(x.s10_close_r.tolist()),
                    "later_high_ge_2r_pct": _pct(int((x.s1_10_high_r >= 2).sum()), int(x.s1_10_high_r.notna().sum())),
                    "later_high_ge_3r_pct": _pct(int((x.s1_10_high_r >= 3).sum()), int(x.s1_10_high_r.notna().sum())),
                    "runner_fire_pct": _pct(int(x.runner_fire.fillna(False).sum()), int(x.runner_fire.notna().sum()))}
    summary["q1_after_early_stop"] = after
    summary["q1"] = q1

    # ── Q2 ──
    def feats(tk, ep_iso, t_date, entry, adr, pattern):
        ser_, ix_ = series.get(tk, []), index.get(tk, {})
        i = ix_.get(t_date)
        j = ix_.get(date.fromisoformat(ep_iso))
        if i is None or j is None or adr is None or adr <= 0 or i <= j:
            return None
        ep = ser_[j]
        c = lambda k: ser_[k][4]
        lows = [ser_[k][3] for k in range(max(j, i - 3), i + 1) if ser_[k][3] is not None]
        highs_before = [ser_[k][2] for k in range(j, i) if ser_[k][2] is not None]
        level = {"ep_low_reclaim": ep[3], "ep_close_reclaim": ep[4], "ep_close_620_prox": ep[4], "ep_high_break": ep[2]}[pattern]
        if pattern == "ep_high_break":
            prior = sum(1 for k in range(j + 1, i) if ser_[k][2] is not None and ser_[k][2] >= level)
        else:
            prior = sum(1 for k in range(j + 1, i) if ser_[k][3] is not None and ser_[k][4] is not None and ser_[k][3] <= level < ser_[k][4])
        out = {"drift3": (c(i - 1) - c(i - 4)) / adr if i - 4 >= 0 and c(i - 1) and c(i - 4) else None,
               "drift1": (c(i - 1) - c(i - 2)) / adr if i - 2 >= 0 and c(i - 1) and c(i - 2) else None,
               "bounce": (entry - min(lows)) / adr if lows else None,
               "intraday": (entry - ser_[i][1]) / adr if ser_[i][1] else None,
               "overhead": (max(highs_before) - entry) / adr if highs_before else None,
               "dist_gap_high": (ep[2] - entry) / adr if ep[2] else None,
               "pos_ep_close": (entry - ep[4]) / adr if ep[4] else None,
               "pos_ep_low": (entry - ep[3]) / adr if ep[3] else None,
               "prior_reclaims": prior, "session_idx": i - j}
        return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in out.items()}

    FEATS = ["drift3", "drift1", "bounce", "intraday", "overhead", "dist_gap_high", "pos_ep_close", "pos_ep_low", "prior_reclaims", "session_idx"]
    fpop = fw[fw.sessions_elapsed >= PRIMARY_K].copy()
    fpop = fpop.merge(R[["id", "cohort", "peak_strict", "r10", "runner_campaign", "runner_fire"]], on="id", how="left")
    q2rows = []
    for r in fpop.itertuples():
        fx = feats(r.ticker, r.ep_date, date.fromisoformat(r.fire_date), float(r.entry_scaled), _f(r.adr_dollar), r.rung)
        if fx is None:
            continue
        q2rows.append({"kind": "fire", "pattern": r.rung, "ticker": r.ticker, "ep_date": r.ep_date, "t": r.fire_date,
                       "rshape": r.reentry_shape, "cohort": r.cohort, "id": r.id,
                       "hit_rec": r.pess_s10, "hit_close": r.close_pess_s10 if isinstance(r.close_pess_s10, str) else None,
                       "hit_fill": r.fill_pess_s10, **fx})
    ctl = cw[(cw.is_fire_session == False) & (cw.sessions_elapsed >= PRIMARY_K)].copy()
    camp_patterns = fpop.groupby(["ticker", "ep_date"]).rung.agg(set).to_dict()
    camp_cohort = R.groupby(["ticker", "ep_date"]).cohort.first().to_dict()
    for r in ctl.itertuples():
        pats = camp_patterns.get((r.ticker, r.ep_date))
        if not pats:
            continue
        for pat in pats:
            fx = feats(r.ticker, r.ep_date, date.fromisoformat(r.session_date), float(r.entry), _f(r.adr_dollar), pat)
            if fx is None:
                continue
            q2rows.append({"kind": "control", "pattern": pat, "ticker": r.ticker, "ep_date": r.ep_date, "t": r.session_date,
                           "rshape": None, "cohort": camp_cohort.get((r.ticker, r.ep_date)), "id": None,
                           "hit_rec": r.pess_s10, "hit_close": r.pess_s10, "hit_fill": None, **fx})
    Q = pd.DataFrame(q2rows)
    Q["y_close"] = np.where(Q.hit_close == "target", 1.0, np.where(Q.hit_close == "stop", 0.0, np.nan))
    Q["y_rec"] = np.where(Q.hit_rec == "target", 1.0, np.where(Q.hit_rec == "stop", 0.0, np.nan))
    # open-at-s10 rows are counted as non-hits in P2's rate (rate = hits / non-abstain); mirror that
    Q["y_close"] = np.where(Q.hit_close.isin(["target", "stop", "open"]), (Q.hit_close == "target").astype(float), np.nan)
    Q["y_rec"] = np.where(Q.hit_rec.isin(["target", "stop", "open"]), (Q.hit_rec == "target").astype(float), np.nan)
    Q.to_csv(HERE / "p7_q2_rows.csv", index=False)

    def decompose(F, C, feat, ycol_f, ycol_c, min_n=20):
        F, C = F[F[feat].notna() & F[ycol_f].notna()], C[C[feat].notna() & C[ycol_c].notna()]
        if len(F) < 30 or len(C) < 60:
            return None
        q1_, q2_ = C[feat].quantile([1 / 3, 2 / 3]).tolist()
        cut = lambda s: np.where(s <= q1_, "T1", np.where(s <= q2_, "T2", "T3"))
        F, C = F.assign(_s=cut(F[feat])), C.assign(_s=cut(C[feat]))
        strata = {}
        pooled_note = []
        for s_ in ("T1", "T2", "T3"):
            fs, cs = F[F._s == s_], C[C._s == s_]
            strata[s_] = {"cut_hi": round(q1_ if s_ == "T1" else q2_ if s_ == "T2" else float(C[feat].max()), 3),
                          "n_fire": int(len(fs)), "n_ctl": int(len(cs)),
                          "fire_rate": _pct(fs[ycol_f].sum(), len(fs)), "ctl_rate": _pct(cs[ycol_c].sum(), len(cs)),
                          "fire_median": _med(fs[feat].tolist()), "ctl_median": _med(cs[feat].tolist())}
            if len(fs) < min_n or len(cs) < min_n:
                pooled_note.append(s_)
        fr, cr = F[ycol_f].mean(), C[ycol_c].mean()
        rw = sum((len(F[F._s == s_]) / len(F)) * (C[C._s == s_][ycol_c].mean() if len(C[C._s == s_]) else cr) for s_ in ("T1", "T2", "T3"))
        return {"n_fire": int(len(F)), "n_ctl": int(len(C)), "fire_rate": round(100 * fr, 2), "ctl_rate": round(100 * cr, 2),
                "gap_pp": round(100 * (fr - cr), 2), "ctl_reweighted_rate": round(100 * rw, 2),
                "within_stratum_pp": round(100 * (fr - rw), 2), "composition_pp": round(100 * (rw - cr), 2),
                "fire_median": _med(F[feat].tolist()), "ctl_median": _med(C[feat].tolist()),
                "strata": strata, "thin_strata_under_20": pooled_note}

    def decompose2d(F, C, ycol_f, ycol_c):
        F, C = F[F.bounce.notna() & F.overhead.notna() & F[ycol_f].notna()], C[C.bounce.notna() & C.overhead.notna() & C[ycol_c].notna()]
        if len(F) < 30 or len(C) < 60:
            return None
        b1, b2 = C.bounce.quantile([1 / 3, 2 / 3]).tolist()
        o1, o2 = C.overhead.quantile([1 / 3, 2 / 3]).tolist()
        lab = lambda d: (np.where(d.bounce <= b1, "B1", np.where(d.bounce <= b2, "B2", "B3")).astype(object)
                         + "x" + np.where(d.overhead <= o1, "O1", np.where(d.overhead <= o2, "O2", "O3")).astype(object))
        F, C = F.assign(_s=lab(F)), C.assign(_s=lab(C))
        fr, cr = F[ycol_f].mean(), C[ycol_c].mean()
        rw, cells, thin = 0.0, {}, []
        for s_ in sorted(set(F._s) | set(C._s)):
            fs, cs = F[F._s == s_], C[C._s == s_]
            crate = cs[ycol_c].mean() if len(cs) else cr
            rw += (len(fs) / len(F)) * crate
            cells[s_] = {"n_fire": int(len(fs)), "n_ctl": int(len(cs)), "fire_rate": _pct(fs[ycol_f].sum(), len(fs)), "ctl_rate": _pct(cs[ycol_c].sum(), len(cs))}
            if len(fs) < 20 or len(cs) < 20:
                thin.append(s_)
        return {"n_fire": int(len(F)), "n_ctl": int(len(C)), "gap_pp": round(100 * (fr - cr), 2),
                "within_stratum_pp": round(100 * (fr - rw), 2), "composition_pp": round(100 * (rw - cr), 2),
                "cells": cells, "thin_cells_under_20": thin}

    q2 = {}
    for pat in ("ALL",) + PATTERNS:
        Fp = Q[(Q.kind == "fire") & ((Q.pattern == pat) if pat != "ALL" else True)]
        Cp = Q[(Q.kind == "control") & ((Q.pattern == pat) if pat != "ALL" else True)]
        if pat == "ALL":
            Cp = Cp.drop_duplicates(subset=["ticker", "ep_date", "t"])
        block = {"n_fire_rows": int(len(Fp)), "n_ctl_rows": int(len(Cp)),
                 "feature_medians": {f_: {"fire": _med(Fp[f_].tolist()), "ctl": _med(Cp[f_].tolist()),
                                          "fire_iqr": _q(Fp[f_].tolist(), (0.25, 0.75)), "ctl_iqr": _q(Cp[f_].tolist(), (0.25, 0.75))} for f_ in FEATS},
                 "shape_split": {sh: {"n": int((Fp.rshape == sh).sum()), "rate_close": _pct(Fp[(Fp.rshape == sh)].y_close.sum(), Fp[(Fp.rshape == sh)].y_close.notna().sum()),
                                      "rate_rec": _pct(Fp[(Fp.rshape == sh)].y_rec.sum(), Fp[(Fp.rshape == sh)].y_rec.notna().sum())}
                                 for sh in ("first", "same_pattern", "new_high_break") if (Fp.rshape == sh).any()},
                 "decomp_close_entry": {f_: decompose(Fp, Cp, f_, "y_close", "y_close") for f_ in FEATS},
                 "decomp_recorded_entry": {f_: decompose(Fp, Cp, f_, "y_rec", "y_close") for f_ in ("bounce", "overhead", "drift3", "pos_ep_close", "prior_reclaims")},
                 "decomp2d_close_entry": decompose2d(Fp, Cp, "y_close", "y_close"),
                 "decomp2d_recorded_entry": decompose2d(Fp, Cp, "y_rec", "y_close")}
        for coh in COHORTS:
            Fc, Cc = Fp[Fp.cohort == coh], Cp[Cp.cohort == coh]
            block[f"cohort_{coh}"] = {"n_fire": int(len(Fc)), "n_ctl": int(len(Cc)),
                                      "fire_rate_close": _pct(Fc.y_close.sum(), Fc.y_close.notna().sum()),
                                      "ctl_rate": _pct(Cc.y_close.sum(), Cc.y_close.notna().sum()),
                                      "fire_rate_rec": _pct(Fc.y_rec.sum(), Fc.y_rec.notna().sum()),
                                      "medians": {f_: {"fire": _med(Fc[f_].tolist()), "ctl": _med(Cc[f_].tolist())} for f_ in ("bounce", "overhead", "drift3", "pos_ep_close")}}
        q2[pat] = block
    summary["q2"] = q2

    # ── Q3 ──
    R = R.merge(Q[Q.kind == "fire"][["id", "drift3", "bounce", "overhead", "pos_ep_close", "prior_reclaims"]], on="id", how="left")
    R["price_bucket"] = pd.cut(R.entry_price, [0, 1, 5, 20, 1e9], labels=["<$1", "$1-5", "$5-20", ">$20"]).astype(str)
    R["ssep_bucket"] = pd.cut(R.sessions_since_ep.fillna(-1), [-2, 0, 1, 2, 5, 10, 999], labels=["unknown", "1", "2", "3-5", "6-10", "11+"]).astype(str)
    R["runup_bucket"] = pd.cut(R.runup_pct, [-1e9, 10, 25, 50, 1e9], labels=["<10%", "10-25%", "25-50%", ">=50%"]).astype(object)
    R["spy_day"] = np.where(R.spy_ret_1d.isna(), None, np.where(R.spy_ret_1d >= 0, "SPY_up", "SPY_down"))
    R["spy_5d"] = np.where(R.spy_ret_5d.isna(), None, np.where(R.spy_ret_5d >= 0, "SPY5_up", "SPY5_down"))
    R["gap_tercile"] = terciles(R.gap_pct)
    R["ep_dv_tercile"] = terciles(R.ep_dollar_volume)
    R["fire_dv_tercile"] = terciles(R.fire_dollar_volume)
    R["score_tercile"] = terciles(R.ep_score)
    R["theme_bucket"] = R.theme.map(lambda v: None if v is None or (isinstance(v, float) and np.isnan(v)) else ("in_theme" if str(v).lower() in ("true", "t", "1") else "not_in_theme"))
    R["catalyst_bucket"] = R.catalyst.where(R.catalyst.notna(), None)
    q3 = {"buckets": {}, "auc": {}}
    for coh in ("ALL",) + COHORTS:
        sub = R if coh == "ALL" else R[R.cohort == coh]
        b = {"cohort": by_bucket(sub, "cohort", COHORTS), "stage": by_bucket(sub, "stage"),
             "price": by_bucket(sub, "price_bucket", ["<$1", "$1-5", "$5-20", ">$20"]),
             "ep_tier": by_bucket(sub, "ep_tier", ["alert_HIGH", "alert_MODERATE_or_none", "scored_below_bar", "rejected_before_scoring"]),
             "ep_score_tercile": by_bucket(sub, "score_tercile"), "catalyst": by_bucket(sub, "catalyst_bucket"),
             "gap_tercile": by_bucket(sub, "gap_tercile"), "sessions_since_ep": by_bucket(sub, "ssep_bucket", ["1", "2", "3-5", "6-10", "11+"]),
             "runup_into_ep": by_bucket(sub, "runup_bucket", ["<10%", "10-25%", "25-50%", ">=50%"]),
             "theme": by_bucket(sub, "theme_bucket"), "spy_day": by_bucket(sub, "spy_day", ["SPY_up", "SPY_down"]),
             "spy_5d": by_bucket(sub, "spy_5d", ["SPY5_up", "SPY5_down"]),
             "ep_dollar_volume_tercile": by_bucket(sub, "ep_dv_tercile"), "fire_dollar_volume_tercile": by_bucket(sub, "fire_dv_tercile"),
             "pattern": by_bucket(sub, "rung", list(PATTERNS)), "shape": by_bucket(sub, "rshape", ["first", "same_pattern", "new_high_break"])}
        q3["buckets"][coh] = b
        traits = ["entry_price", "gap_pct", "ep_score", "sessions_since_ep", "runup_pct", "ep_dollar_volume", "fire_dollar_volume",
                  "adr20_pct", "stop_width_pct", "spy_ret_1d", "spy_ret_5d", "drift3", "bounce", "overhead", "pos_ep_close", "prior_reclaims"]
        aucs = {}
        for lab, mask_pop in (("runner_campaign", sub.runner_label_pop == True), ("runner_fire", sub.runner_fire.notna())):
            pop = sub[mask_pop]
            y = pop[lab].fillna(False).astype(bool)
            aucs[lab] = {"n_pop": int(len(pop)), "n_runners": int(y.sum())}
            for tr in traits:
                dark = _pct(int(pop[tr].isna().sum()), len(pop))
                res = auc_ci(pop.loc[y, tr].tolist(), pop.loc[~y, tr].tolist())
                res["dark_pct"] = dark
                if dark is not None and dark > 50:
                    res["DARK"] = True
                aucs[lab][tr] = res
        q3["auc"][coh] = aucs
    summary["q3"] = q3

    # ── Q4 ──
    def ep13(tk, ep_iso, adr):
        ser_, ix_ = series.get(tk, []), index.get(tk, {})
        j = ix_.get(date.fromisoformat(ep_iso))
        if j is None or j + 3 >= len(ser_):
            return None
        ep = ser_[j]
        nxt = ser_[j + 1:j + 4]
        closes = [b[4] for b in nxt]
        lows = [b[3] for b in nxt]
        if None in closes or None in lows or not ep[4] or not ep[3]:
            return None
        cls_ = "FAILED" if min(closes) < ep[3] else ("FADED" if min(closes) < ep[4] else "HELD")
        first_fail = next((i + 1 for i, c in enumerate(closes) if c < ep[3]), None)
        return {"ep13": cls_, "ep13_first_fail_session": first_fail, "depth_adr": round((ep[4] - min(lows)) / adr, 3) if adr else None,
                "d1_move_adr": round((closes[0] - ep[4]) / adr, 3) if adr else None}
    adr_by_camp = fw.groupby(["ticker", "ep_date"]).adr_dollar.first().to_dict()
    camp_rows = []
    for (tk, ep_iso) in set(zip(R.ticker, R.ep_date)):
        e = ep13(tk, ep_iso, _f(adr_by_camp.get((tk, ep_iso))))
        if e:
            camp_rows.append({"ticker": tk, "ep_date": ep_iso, **e})
    E = pd.DataFrame(camp_rows)
    R = R.merge(E, on=["ticker", "ep_date"], how="left")
    R["entry_vs_ep"] = np.where(R.ep_low.isna() | R.entry_price.isna(), None,
                        np.where(R.entry_price * R.scale < R.ep_low, "below_EP_low",
                        np.where(R.entry_price * R.scale < R.ep_close, "EP_low_to_close",
                        np.where(R.entry_price * R.scale <= R.ep_high, "EP_close_to_high", "above_EP_high"))))
    q4 = {}
    for coh in ("ALL",) + COHORTS:
        sub = R if coh == "ALL" else R[R.cohort == coh]
        camps_sub = sub.drop_duplicates(subset=["ticker", "ep_date"])
        q4[coh] = {"campaigns_by_ep13": camps_sub.ep13.value_counts(dropna=False).to_dict(),
                   "fires_by_ep13": by_bucket(sub, "ep13", ["HELD", "FADED", "FAILED"]),
                   "fires_by_entry_vs_ep": by_bucket(sub, "entry_vs_ep", ["below_EP_low", "EP_low_to_close", "EP_close_to_high", "above_EP_high"]),
                   "fires_by_ep13_x_pattern": {pat: by_bucket(sub[sub.rung == pat], "ep13", ["HELD", "FADED", "FAILED"]) for pat in PATTERNS},
                   "depth_adr": _q(camps_sub.depth_adr.tolist()), "d1_move_adr": _q(camps_sub.d1_move_adr.tolist()),
                   "runner_campaigns_by_ep13": camps_sub[camps_sub.runner_campaign == True].ep13.value_counts(dropna=False).to_dict(),
                   "nonrunner_campaigns_by_ep13": camps_sub[(camps_sub.runner_campaign == False)].ep13.value_counts(dropna=False).to_dict(),
                   "first_fail_session": camps_sub.ep13_first_fail_session.value_counts(dropna=False).to_dict()}
    # ADDED AFTER Q4 WAS READ (declared as such in the doc): the HELD / FADED / FAILED label uses the
    # closes of sessions 1-3 after the EP, so for a fire at session 1-3 it contains the future. The
    # label is knowable AT ENTRY only for fires at session >= 4 — that subset is the tradable read.
    q4["label_knowable_at_entry_s4plus"] = {}
    for coh in ("ALL",) + COHORTS:
        sub = R if coh == "ALL" else R[R.cohort == coh]
        sub = sub[sub.sessions_since_ep >= 4]
        q4["label_knowable_at_entry_s4plus"][coh] = {"n_fires": int(len(sub)),
            "fires_by_ep13": by_bucket(sub, "ep13", ["HELD", "FADED", "FAILED"]),
            "fires_by_ep13_x_pattern": {pat: by_bucket(sub[sub.rung == pat], "ep13", ["HELD", "FADED", "FAILED"]) for pat in PATTERNS}}
    summary["q4"] = q4

    # ── loss shares + the joint table ──
    S = R[R.r10.notna() & R.floored].copy()
    tot = float(S.r10.sum())
    S["same_session_stop"] = S.stop_idx == 0
    S["failed_ep"] = S.ep13 == "FAILED"
    S["reentry"] = S.rshape != "first"
    S["sub5"] = S.entry_price < 5
    joint = {}
    for a_ in (False, True):
        for b_ in (False, True):
            for c_ in (False, True):
                m = S[(S.same_session_stop == a_) & (S.failed_ep == b_) & (S.reentry == c_)]
                if len(m):
                    joint[f"same_session_stop={a_}|failed_ep={b_}|reentry={c_}"] = {"n": int(len(m)), "sum_r10": round(float(m.r10.sum()), 2),
                                                                                    "share_pct": _pct(float(m.r10.sum()), tot), "mean_r10": _mean(m.r10.tolist())}
    summary["loss_shares"] = {"total_r10": round(tot, 2), "n": int(len(S)),
                              "by_cohort": {c_: {"n": int((S.cohort == c_).sum()), "sum_r10": round(float(S[S.cohort == c_].r10.sum()), 2), "share_pct": _pct(float(S[S.cohort == c_].r10.sum()), tot)} for c_ in COHORTS},
                              "same_session_stop": {"n": int(S.same_session_stop.sum()), "share_pct": _pct(float(S[S.same_session_stop].r10.sum()), tot)},
                              "stopped_by_s2": {"n": int((S.stop_idx <= 2).sum()), "share_pct": _pct(float(S[S.stop_idx <= 2].r10.sum()), tot)},
                              "failed_ep": {"n": int(S.failed_ep.sum()), "share_pct": _pct(float(S[S.failed_ep].r10.sum()), tot)},
                              "reentry": {"n": int(S.reentry.sum()), "share_pct": _pct(float(S[S.reentry].r10.sum()), tot)},
                              "sub_5_dollar": {"n": int(S.sub5.sum()), "share_pct": _pct(float(S[S.sub5].r10.sum()), tot)},
                              "green_then_stopped": {"n": int(S.path.str.startswith("GREEN").sum()), "share_pct": _pct(float(S[S.path.str.startswith("GREEN")].r10.sum()), tot)},
                              "joint": joint}
    R.to_csv(HERE / "p7_rows.csv", index=False)
    with open(HERE / "p7_summary.json", "w") as fh:
        json.dump(summary, fh, indent=1, default=str)
    print("Q1 ALL|ALL:", json.dumps(q1["ALL|ALL"], default=str)[:1500])
    print("loss shares:", json.dumps(summary["loss_shares"], default=str)[:1200])
    print("wrote p7_summary.json, p7_rows.csv, p7_q2_rows.csv")


if __name__ == "__main__":
    main()
