"""#327 — a daily-range stop COMBINED WITH re-entries, on the 277 real EPs the system caught.
2026-09-27 (Sunday build slot). $0: worked ENTIRELY from the 09-26 rerun's captured files in this folder
(no prod access, no new bars). No toggle, no table, no deploy, no PLAN.md line, no live code touched.

WHY. The right-population rerun (327_real_ep_rerun_2026-09-26.md) found the loss is made at the STOP: 62% of
the lane's first attempts are stopped; on the 7 big-runner EPs the lane's tight stop kept 4 of 11 first fires at
>= 3R where a 1xADR stop keeps 7-9. Operator 2026-09-26: "we can explore reentries along with everything else you
suggested". The 09-02 retry test (545_retry_test_2026-09-02.md) on the May-Aug subset found one cell family on
ep_low_reclaim carried by TWO names (NRIX, EFOR); it was never read on the whole population, never era-split,
never judged after dropping two names, and never judged on gap-charged stops.

THE QUESTION. On the 277 real EPs, does a daily-range stop (0.75 / 1.0 / 1.5 x ADR$) combined with up to 1/2/3
re-entries after a stop-out make any of the lane's four patterns pay, in BOTH rule eras, robustly?

═══════════════════════════ STEP 0 — THE POPULATION GATE (phase `gate`; HALT on any mismatch) ═══════════════════════════
Population = every live-source mi_ep_alerts row (COALESCE(source,'live')='live') 2026-05-01 -> 2026-09-11, one
campaign per (ticker, alert_date) — the rerun's gate.sql, captured in gate_out.txt. This probe recomputes every
gate line from the files it actually loads (alerts.tsv, campaigns.tsv, fires.tsv) and compares them to
gate_out.txt line by line:
    ERA A (alert_date < 2026-08-22): 261 campaigns, 243 names, HIGH 184 / MODERATE 66 / other 11, alert dates
           05-11 -> 08-21, 0 priced under $5; TEAM 2026-08-07, MRNA 2026-08-19, PLTR 08-04, HTFL 08-14 present.
    ERA B (alert_date >= 2026-08-22): 16 campaigns, 16 names, HIGH 14 / MODERATE 2.
    ALL: 277 campaigns, 256 names.
Also: every fires.tsv campaign is one of the 277; the lane-recorded first fires are exactly the 23 rows on the
10 uncovered ERA B campaigns (the rerun's pre-registered substitution). mi_delayed_entry_trigger rows are NEVER
the population. Any mismatch -> a HALT note in the doc and stop.

═══════════════════════════ INSTRUMENT (reused, not rewritten) ═══════════════════════════
- FIRST ATTEMPTS = the rerun's fires.tsv: 632 first-attempt fires (609 replayed through the 09-01 walker with the
  horizon patched to 2026-09-25 and the < 100-bar session = MISSING rule; 23 lane-recorded on the uncovered ERA B
  campaigns). Bars = the rerun's daily.tsv / minute.tsv.gz through the rerun's own loaders (`rerun.load_*`).
- RE-ENTRY SHAPES = the 09-02 retry test's functions, imported from `_545_retry_test.py` (`_search_reentry`,
  `_reentry_same_pattern_reclaim`, `_reentry_same_pattern_620`, `_reentry_level`, `_locate_first_fire`,
  `_locate_level_touch`) — themselves line-for-line mirrors of the lane's `_record_reentries_for` /
  `_replay_same_pattern_reclaim` / `_replay_same_pattern_620` / `replay_level_break`. Policy "either" = whichever of
  same_pattern / new_high_break fires first after a stop-out (same-day tie -> same_pattern). A re-entry opens ONLY
  after a STOP-OUT; a trail exit or the 20th-session time exit ends the campaign. Each stop-out opens a fresh
  20-session window (REENTRY_WATCH_SESSIONS) from the session AFTER the stop day; windows chain.
- SETTLEMENT = the lane's `compute_settlement` (pure) on every attempt, with the rerun's day-0 source order:
  real post-fire 5-min bars -> (lane-recorded first fires only) the row's cached day-0 excursion through the
  production `day0_pseudo_bars` -> None (ABSTAIN when the day low reached the stop). The 09-02 `_settle` is NOT
  imported: it passes [] for missing day-0 bars, which `compute_settlement` reads as "fire was the last bar".
- MARK AT THE HORIZON: `compute_settlement` abstains ("window_open") when fewer than 20 sessions exist and no stop
  hit. Such an attempt is MARKED at the last daily close (09-25); the trail arm exits at the first close below the
  real `sma_trail_line` on the same closes (compute_settlement's own rule re-applied) — anchored (C) below.
- THE ABSTAIN RULE: a session a re-entry search needs minutes for with none stored is BLIND (facts fold, no fire,
  COUNTED per cell); a settlement that cannot complete abstains and the campaign is unreadable under that cell
  (counted). On the 10 uncovered ERA B campaigns essentially every same-pattern search is blind — said so.
- STOP FOR EVERY ATTEMPT: "incumbent" = the attempt's OWN lane stop (the undercut low / dip low / 620 day-low-so-
  far / the level fire's prior-session low — exactly as the lane stamps a re-entry row); "adr_075/100/150" = that
  attempt's entry - k x ADR$ with the EP-anchored ADR$ (compute_ep_adr_dollar, fixed per campaign).
- GAP-THROUGH ACCOUNTING (the JUDGED R): a stop at session s >= 1 whose session OPENED below the stop fills at the
  open: R = (open - entry) / risk (the rerun's `gap_charged`). Day-0 stops and trail/time exits are not charged.
  The house -1.00R total is reported beside it. The stop DAY that opens the next window is unchanged.
- WIDTH FLOOR: Block 5's standing 0.5% floor — an attempt whose stop is under 0.5% wide is counted, not scored;
  its campaign is unreadable under that cell (counted). It bites only the incumbent stop.
- EXIT ARMS: "trail" = the lane's own arm (close below max(SMA10, SMA20), stop live); "none" = the lane's M-none
  arm (stop, else the 20th-session close — SETTLE_HOLD_SESSIONS). "Hold to horizon" is read as M-none: a literal
  hold to 09-25 would give May EPs a four-month hold and make the eras incomparable. Anything still open at
  09-25 is marked at that close. ERA B never reaches 20 sessions (13-19 available) — every unstopped ERA B chain
  is a horizon mark, stated in the doc.
- UNIT = per-CAMPAIGN total R at equal dollar risk per attempt (each attempt risks 1R in its own units; summing
  attempts sums equal-dollar bets). A per-trade average is not an output.
- READABILITY: a campaign is readable in a cell unless an attempt abstains or is floored. A re-entry window the
  horizon cut short with no fire stays IN with its realized total and is COUNTED as "window censored" — that
  count is the plain statement of ERA B's shorter horizon.
- ONE chain per (first fire x stop x arm), up to 4 attempts, policy "either" only: 632 x 4 x 2 = 5,056 chains;
  the attempts=1/2/3/4 columns are prefixes (1 = no re-entry baseline; 2/3/4 = up to 1/2/3 re-entries).

═══════════════════════════ ANCHORS (phase `anchor`, printed before any cell) ═══════════════════════════
(A) CHAIN LOGIC: this probe's `run_chain` on the 09-02 test's OWN files (`_562bf_*` + `_562sp_extra_minutes`,
    horizon 08-31, stops 0.25/0.50/0.75/1.00 x ADR$, both arms, policy either, unlimited attempts) must reproduce
    `_545rt_rows.tsv` row-for-row on EVERY attempt (shape, fire date, minute, entry, stop, status, outcome, R,
    stop day, window length/full/blind) — the only anchor that tests attempts >= 2. Expected: 0 drift, except
    where the 09-02 `_settle`'s [] trap fired (classified if any).
(B) FIRST ATTEMPT AT 09-25, INCUMBENT STOP: attempt 1 of every fires.tsv row vs the rerun's own
    outcome / realized_r / outcome_trail / realized_r_trail — 609 replayed rows expected 0 drift; the 23
    lane-recorded rows reported separately (their reference is the lane's live settlement).
(C) THE MARK: for settled fires with >= 20 sessions, the session list truncated to 10 must give the same R as
    `compute_settlement`'s own r_none_s10 / r_trail_s10 (mark-to-market at session 10 by construction).

═══════════════════════════ THE GRID (pre-registered; written before any cell was computed) ═══════════════════════════
pattern {ep_low_reclaim, ep_close_reclaim, ep_high_break, ep_close_620_prox}
  x stop {incumbent, 0.75, 1.0, 1.5 x ADR$}
  x attempts {1, 2, 3, 4}
  x exit {trail max(SMA10,SMA20), none (M-none)}                       = 128 cells, 8 of them the baselines
    (attempts=1 x incumbent stop x arm), 120 draws. Cells are NESTED (prefix caps, adjacent stops), so the
    effective number of independent draws is far smaller than 120.
NOISE BAND (Block 5's 1-3 of 294 and the rerun's 7 of 654, scaled): <= 2 of 120 clearing ERA A is noise;
    >= 11 is a family.
PASS BAR per cell, judged in ERA A on the gap-charged per-campaign totals:
  (1) mean per-campaign R > 0;
  (2) total R > 0 after dropping the best TWO NAMES by summed R;
  (3) the judged R charges gap-through stops at the open (above);
  (4) beats the same pattern's attempts=1 x incumbent-stop x SAME-arm cell on total R, PAIRWISE on the campaigns
      readable under both cells (the day-0 abstain set differs by stop width); the lane's own arm (incumbent x
      trail) is shown beside it;
  (5) worst single-NAME cumulative drawdown (running sum of gap-charged R across the name's chain(s)) no worse than
      the baseline's worst on the same pairwise set minus the extra attempts' nominal risk: worst_cell >=
      worst_base - (attempts - 1)  (the 545 clause);
  (6) n >= 30 readable ERA A campaigns;
  (7) ERA B mean per-campaign R has the SAME SIGN as ERA A's, ERA B's n stated; 0 ERA B campaigns = not confirmed.
DECLARED OUTCOMES: (i) cells clear ERA A and ERA B confirms -> named, fork for him; (ii) clear ERA A, none
    confirmed -> "eras disagree", stop there; (iii) zero clear ERA A -> re-entry does not rescue the lane on real
    EPs; the lane ruling goes back to him.
EXPECTED RESULT, stated before running: most likely (iii) — the 09-02 best cell loses about -15R once NRIX and EFOR
    are dropped.
ALSO REPORTED (descriptive, never a pass): per cell, campaigns reaching >= 3R total; how many of the rerun's 7
    big-runner EPs (HQ, TE, ALOY, ARM, EFOR, VPG, NRIX — read from summary.json, never hand-listed) end >= 3R;
    TEAM 2026-08-07 walked by hand in the best-by-ERA-A-total cell of each pattern (TEAM fired only on
    ep_close_reclaim and ep_close_620_prox — the other two patterns say so).

Usage:
    python3 reentry.py gate      -> gate_reentry_out.txt   (HALTs on mismatch)
    python3 reentry.py anchor    -> anchor_out.txt
    python3 reentry.py run       -> reentry_rows.tsv, reentry_chains.tsv   (run ONCE; read the files)
    python3 reentry.py report    -> reentry_cells.tsv, reentry_report.txt, reentry_summary.json
"""
from __future__ import annotations

import csv
import json
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
for p in (REPO, REPO / "scripts" / "probes", REPO / "scripts" / "probes" / "_327_block5", HERE):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import rerun                                      # noqa: E402  the 09-26 rerun: loaders, gap_charged, constants
import _545_retry_test as rt                      # noqa: E402  the 09-02 retry test: the re-entry shapes
import _562_backfill_replay as bf                 # noqa: E402  the 09-01 walker (anchor A's first fires)
import _562_stop_population_probe as sp           # noqa: E402  the 09-02 extra minutes
from agents.market_intelligence.delayed_entry_shadow import (   # noqa: E402  real code
    REENTRY_WATCH_SESSIONS, SETTLE_HOLD_SESSIONS, _trading_days, compute_ep_adr_dollar, compute_settlement,
    day0_pseudo_bars, sma_trail_line,
)

HORIZON = date(2026, 9, 25)
ERA_SPLIT = date(2026, 8, 22)
PATTERNS = rerun.PATTERNS
STOPS = ("incumbent", "adr_075", "adr_100", "adr_150")
ADR_MULT = {"adr_075": 0.75, "adr_100": 1.0, "adr_150": 1.5}
CAPS = (1, 2, 3, 4)
ARMS = ("trail", "none")
POLICY = "either"
MAX_ATTEMPTS = 4
WIDTH_FLOOR_PCT = 0.5
TAIL_R = 3.0
N_CELLS = len(PATTERNS) * len(STOPS) * len(CAPS) * len(ARMS)
N_BASELINES = len(PATTERNS) * len(ARMS)
NOISE_MAX, FAMILY_MIN = 2, 11
PASS_N = 30
_EPS = 1e-9
TEAM = ("TEAM", date(2026, 8, 7))

ROW_COLS = ["ticker", "ep_date", "era", "tier", "source", "rung", "stop", "arm", "attempt", "shape", "fire_date",
            "fire_minute", "resolution", "derived_touch", "entry", "stop_px", "stop_w", "status", "outcome", "r",
            "r_gap", "gap_through", "mfe_r", "mae_r", "day0_pess_stop", "d0_kind", "stop_day", "stop_session_idx",
            "marked_at", "win_len", "win_full", "win_blind", "win_missing"]
CHAIN_COLS = ["ticker", "ep_date", "era", "rung", "stop", "arm", "n_attempts", "end", "ties", "blind", "missing"]


def _f(v):
    return rerun._f(v)


def _sql_median(vals):
    """percentile_cont(0.5) then round(numeric, 2) as Postgres does it: the exact decimal mid-point of the two
    middle values (even n) rounded half away from zero."""
    v = sorted(Decimal(str(x)) for x in vals)
    n = len(v)
    m = v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2
    return m.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _stop_label(stop_mode):
    return stop_mode if isinstance(stop_mode, str) else f"adr_{int(round(stop_mode * 100)):03d}"


# ── settlement: the lane's compute_settlement + the rerun's day-0 source order + the horizon mark ─────────

def mark_at_horizon(entry, stop, fire_day_bar, sessions, bars, closes_before):
    """`compute_settlement` returned abstain:window_open — it walked EVERY available session (none missing),
    hit no stop, and ran out of sessions before the 20th. Mark both arms at the last close; the trail arm exits
    at the first close below the real sma_trail_line, applied to the same closes in the same order
    (compute_settlement's own day-0-then-sessions rule). Anchored against r_none_s10 / r_trail_s10 (anchor C)."""
    risk = entry - stop
    f_c = fire_day_bar["c"]
    closes = [c for c in closes_before if c is not None] + [f_c]
    trail_exit = None
    line = sma_trail_line(closes)
    if line is not None and f_c < line:
        trail_exit = (0, f_c)
    last_c, last_i = f_c, 0
    hi_max, lo_min = fire_day_bar["h"], fire_day_bar["l"]
    for i, d in enumerate(sessions, start=1):
        b = bars[d]
        c = b["close"]
        closes.append(c)
        last_c, last_i = c, i
        hi_max, lo_min = max(hi_max, b["high_price"]), min(lo_min, b["low_price"])
        if trail_exit is None:
            line = sma_trail_line(closes)
            if line is not None and c < line:
                trail_exit = (i, c)
    r_none = round((last_c - entry) / risk, 4)
    out = {"status": "marked", "outcome": "open", "realized_r": r_none, "stop_session_idx": None,
           "marked_at": last_i, "mfe_r": round((hi_max - entry) / risk, 4), "mae_r": round((lo_min - entry) / risk, 4)}
    if trail_exit is not None:
        out["outcome_trail"], out["realized_r_trail"] = "trail_exit", round((trail_exit[1] - entry) / risk, 4)
    else:
        out["outcome_trail"], out["realized_r_trail"] = "open", r_none
    return out


def settle_attempt(ctx, minutes, entry, stop, fire_date, fm, horizon, d0_cache=None, mark=True):
    """One attempt through the lane's own `compute_settlement`. Day-0 source order = the rerun's build_row:
    real post-fire 5-min bars -> (lane-recorded first fires) the cached excursion via the production
    `day0_pseudo_bars` -> None (compute_settlement ABSTAINS when the day low reached the stop). Never []."""
    bars = ctx["bars"]
    fb = bars.get(fire_date) or {}
    fire_day_bar = {"h": fb.get("high_price"), "l": fb.get("low_price"), "c": fb.get("close")}
    post5, d0_kind = None, "daily_fold" if fm is None else "no_source"
    if fm is not None:
        bars5 = minutes.get((ctx["tkr"], fire_date), [])
        if bars5:
            post5, d0_kind = [b for b in bars5 if b["m"] > fm], "real_intraday_bars"
        elif d0_cache is not None:
            pb = day0_pseudo_bars(*d0_cache)
            if pb is not None:
                post5, d0_kind = pb, "cached_pseudo_bars"
    sessions = _trading_days(fire_date + timedelta(days=1), horizon)
    closes_before = [bars[d]["close"] for d in ctx["ordered"] if d < fire_date and bars[d]["close"] is not None]
    res = compute_settlement(entry=entry, stop=stop, fire_minute=fm, fire_day_bar=fire_day_bar, post_fire_bars5=post5,
                             sessions=sessions, bars_by_day=bars, closes_before_fire=closes_before)
    if mark and res["status"] == "abstain" and res.get("reason") == "window_open":
        res = mark_at_horizon(entry, stop, fire_day_bar, sessions, bars, closes_before)
    res["_sessions"] = sessions
    res["_d0_kind"] = d0_kind
    return res


# ── the chain ────────────────────────────────────────────────────────────────────────────────────────

def run_chain(rung, ctx, first, stop_mode, arm, minutes, horizon, max_attempts=MAX_ATTEMPTS, d0_cache=None, mark=True):
    """Up to `max_attempts` (0 = unlimited) attempts: the recorded first fire, then after every STOP-OUT the
    09-02 test's re-entry search (policy `either`) in a 20-session window from the session after the stop day.
    Stop per attempt: its own lane stop ("incumbent") or entry - k x ADR$. R per attempt in its own units;
    r_gap charges a stop at session >= 1 whose session opened below the stop at that open."""
    adr = ctx["adr"]
    bars = ctx["bars"]
    attempts = []
    entry, fire_date = float(first["entry"]), first["fire_date"]
    own_stop = _f(first.get("stop"))
    fm, derived = rt._locate_first_fire(first, ctx, minutes)
    shape = "first"
    end, ties, blind, missing = None, 0, 0, 0
    blind_days = set()
    while True:
        idx = len(attempts) + 1
        row = {"attempt": idx, "shape": shape, "fire_date": fire_date, "fire_minute": fm,
               "resolution": "minute_5" if fm is not None else "daily", "derived_touch": derived, "entry": entry,
               "stop_px": None, "stop_w": None, "status": None, "outcome": None, "r": None, "r_gap": None,
               "gap_through": False, "mfe_r": None, "mae_r": None, "day0_pess_stop": False, "d0_kind": None,
               "stop_day": None, "stop_session_idx": None, "marked_at": None,
               "win_len": None, "win_full": None, "win_blind": None, "win_missing": None}
        if stop_mode == "incumbent":
            stop = own_stop
            if stop is None:
                row["status"] = "abstain_no_own_stop"; attempts.append(row); end = "abstain"; break
        else:
            if adr is None or adr <= 0:
                row["status"] = "abstain_no_stop_basis"; attempts.append(row); end = "abstain"; break
            stop = entry - stop_mode * adr
        row["stop_px"] = stop
        row["stop_w"] = (entry - stop) / entry * 100.0 if entry else None
        if stop >= entry or stop <= 0:
            row["status"] = "killed_entry_le_stop"; attempts.append(row); end = "abstain"; break
        res = settle_attempt(ctx, minutes, entry, stop, fire_date, fm, horizon,
                             d0_cache=(d0_cache if idx == 1 else None), mark=mark)
        row["status"], row["d0_kind"] = res["status"], res["_d0_kind"]
        if res["status"] not in ("settled", "marked"):
            row["outcome"] = res.get("reason"); attempts.append(row); end = "abstain"; break
        if arm == "none":
            outcome, r = res["outcome"], res["realized_r"]
        else:
            outcome, r = res["outcome_trail"], res["realized_r_trail"]
        row["outcome"], row["r"], row["r_gap"] = outcome, r, r
        row["mfe_r"], row["mae_r"], row["marked_at"] = res.get("mfe_r"), res.get("mae_r"), res.get("marked_at")
        fb = bars.get(fire_date) or {}
        row["day0_pess_stop"] = (fm is None and fb.get("low_price") is not None and fb["low_price"] <= stop)
        if outcome == "stop":
            sidx = res["stop_session_idx"]
            row["stop_session_idx"] = sidx
            stop_day = fire_date if sidx == 0 else res["_sessions"][sidx - 1]
            row["stop_day"] = stop_day
            if sidx >= 1:
                o = (bars.get(stop_day) or {}).get("open_price")
                if o is not None and o < stop:
                    row["r_gap"] = round((o - entry) / (entry - stop), 4)
                    row["gap_through"] = True
        attempts.append(row)
        if outcome != "stop":
            end = "open_at_horizon" if outcome == "open" else "exit"
            break
        if max_attempts and idx >= max_attempts:
            end = "capped"
            break
        window = _trading_days(stop_day + timedelta(days=1), horizon)[:REENTRY_WATCH_SESSIONS]
        window_full = len(window) == REENTRY_WATCH_SESSIONS
        hit, m, bl, tie = rt._search_reentry(rung, POLICY, ctx, window, stop_day, minutes)
        missing += m
        blind += len(bl)
        blind_days.update(bl)
        ties += int(tie)
        row["win_len"], row["win_full"], row["win_blind"], row["win_missing"] = len(window), window_full, len(bl), m
        if hit is None:
            end = "no_reentry" if window_full else "censored_window"
            break
        fire = hit["fire"]
        entry, fire_date, shape = float(fire["entry"]), hit["fire_date"], hit["shape"]
        own_stop = _f(fire.get("stop"))
        fm = fire.get("fire_minute")
        derived = False
        if fm is None:
            fm, derived = rt._locate_level_touch(entry, fire_date, ctx, minutes)
    return attempts, end, {"ties": ties, "blind": blind, "missing": missing, "blind_days": blind_days}


# ── loaders (the rerun's files) ────────────────────────────────────────────────────────────────────────

def load_campaigns():
    out = {}
    for r in rerun.read_tsv(HERE / "campaigns.tsv"):
        k = (r["ticker"], date.fromisoformat(r["ep_date"]))
        out[k] = {**r, "ep_date": k[1], "adr_dollar": _f(r["adr_dollar"]), "cov_have": int(r["cov_have"] or 0),
                  "cov_sessions": int(r["cov_sessions"] or 0)}
    return out


def make_ctx(f, daily):
    bars = daily[f["ticker"]]
    return {"tkr": f["ticker"], "ep": f["ep_date"], "bars": bars, "ordered": sorted(bars),
            "gl": f["ep_low"], "gc": f["ep_close"], "gh": f["ep_high"], "adr": f["adr_dollar"]}


def load_runners():
    """The rerun's 7 big-runner EPs, keyed (ticker, iso ep_date) like the row keys — read, never hand-listed."""
    s = json.loads((HERE / "summary.json").read_text())
    return {(k.split("|")[0], k.split("|")[1]) for k in s["D_big_winners"]["runners"]}


# ── phase: gate ──────────────────────────────────────────────────────────────────────────────────────

def phase_gate():
    alerts = rerun.load_alerts()
    camps = load_campaigns()
    fires = rerun.load_fires()
    gate = defaultdict(dict)
    for r in rerun.read_tsv(HERE / "gate_out.txt"):
        gate[r["era"]][r["k"]] = r["v"]
    got = defaultdict(dict)
    for era in ("A", "B"):
        rows = [a for a in alerts if a["era"] == era]
        assert all((a["ep_date"] < ERA_SPLIT) == (era == "A") for a in rows), "era label vs alert_date"
        got[era]["campaigns"] = str(len(rows))
        got[era]["names"] = str(len({a["ticker"] for a in rows}))
        for t, n in Counter(a["tier"] for a in rows).items():
            got[era][f"tier_{t}"] = str(n)
        got[era]["first_alert_date"] = str(min(a["ep_date"] for a in rows))
        got[era]["last_alert_date"] = str(max(a["ep_date"] for a in rows))
        for m, n in Counter(str(a["ep_date"])[:7] for a in rows).items():
            got[era][f"month_{m}"] = str(n)
        # medians rounded the way gate.sql rounds them: round(numeric, 2) = half AWAY from zero on the exact
        # decimal. Python's f"{:.2f}" on the binary float rounds 114.885 -> 114.88 and 10.895 -> 10.89 (the two
        # ERA B medians sit exactly on a half-cent); the first gate run flagged exactly those two lines.
        got[era]["median_prior_close"] = str(_sql_median([a["prior_close"] for a in rows]))
        got[era]["median_gap_pct"] = str(_sql_median([a["gap_pct"] for a in rows]))
        for a in rows:
            if (a["ticker"], a["ep_date"]) in {("TEAM", date(2026, 8, 7)), ("MRNA", date(2026, 8, 19)),
                                                ("PLTR", date(2026, 8, 4)), ("HTFL", date(2026, 8, 14))}:
                got[era][f"has_{a['ticker']}_{a['ep_date']}"] = "1"
        got[era]["_under_5"] = sum(1 for a in rows if a["prior_close"] is not None and a["prior_close"] < 5)
        got[era]["_prior_close_null"] = sum(1 for a in rows if a["prior_close"] is None)
    got["ALL"]["campaigns"] = str(len(alerts))
    got["ALL"]["names"] = str(len({a["ticker"] for a in alerts}))
    lines, ok = [], True
    for era in ("A", "B", "ALL"):
        keys = sorted(set(gate[era]) | {k for k in got[era] if not k.startswith("_")})
        for k in keys:
            g, m = gate[era].get(k), got[era].get(k)
            same = g == m
            ok &= same
            lines.append(f"{'ok ' if same else 'MISMATCH'} {era:3s} {k:28s} gate_out={g!s:12s} loaded={m!s}")
        if era != "ALL":
            u5, nul = got[era]["_under_5"], got[era]["_prior_close_null"]
            same = (u5 == 0 and nul == 0 and "prior_close_lt5" not in gate[era])
            ok &= same
            lines.append(f"{'ok ' if same else 'MISMATCH'} {era:3s} {'prior_close_lt5':28s} gate_out={'(no row = 0)':12s} loaded={u5} (null {nul})")
    # campaigns.tsv and fires.tsv belong to the same 277
    ak = {(a["ticker"], a["ep_date"]) for a in alerts}
    same = set(camps) == ak
    ok &= same
    lines.append(f"{'ok ' if same else 'MISMATCH'} campaigns.tsv keys == alerts.tsv keys: {len(camps)} vs {len(ak)}")
    fk = {(f["ticker"], f["ep_date"]) for f in fires}
    same = fk <= ak
    ok &= same
    lines.append(f"{'ok ' if same else 'MISMATCH'} fires.tsv campaigns subset of the 277: {len(fk)} campaigns, {len(fires)} first fires "
                 f"(ERA A {sum(1 for f in fires if f['era'] == 'A')}, ERA B {sum(1 for f in fires if f['era'] == 'B')})")
    lane = [f for f in fires if f["source"] == "lane_recorded"]
    unc = {k for k, c in camps.items() if c["era"] == "B" and c["cov_sessions"] and c["cov_have"] < rerun.COVERAGE_MIN_FRAC * c["cov_sessions"]}
    same = len(lane) == 23 and all((f["ticker"], f["ep_date"]) in unc for f in lane) and len(unc) == 10
    ok &= same
    lines.append(f"{'ok ' if same else 'MISMATCH'} lane-recorded first fires = 23 on the 10 uncovered ERA B campaigns: "
                 f"{len(lane)} rows on {len({(f['ticker'], f['ep_date']) for f in lane})} campaigns; uncovered ERA B campaigns {len(unc)} "
                 f"{sorted(k[0] for k in unc)}")
    era_a_alert_dates = {a["ep_date"] for a in alerts if a["era"] == "A"}
    lines.append(f"    ERA A alert dates {min(era_a_alert_dates)} -> {max(era_a_alert_dates)}; "
                 f"ERA B sessions after the alert through {HORIZON}: "
                 + ", ".join(f"{a['ticker']} {a['ep_date']}: {len(_trading_days(a['ep_date'] + timedelta(days=1), HORIZON))}"
                             for a in sorted((a for a in alerts if a['era'] == 'B'), key=lambda a: a['ep_date'])))
    txt = "\n".join(lines) + f"\n\nGATE {'PASSED' if ok else 'FAILED — HALT'}\n"
    (HERE / "gate_reentry_out.txt").write_text(txt)
    print(txt)
    if not ok:
        sys.exit(1)


# ── phase: anchor ────────────────────────────────────────────────────────────────────────────────────

def _cmp(a, b, tol=1e-6):
    if a is None or b is None:
        return a is None and b is None
    return abs(float(a) - float(b)) <= tol


def phase_anchor():
    out = []

    # (A) chain logic on the 09-02 test's own files, horizon 08-31, unlimited attempts, no marking
    bf.LAST_DATA_DAY = date(2026, 8, 31)
    alerts, daily = bf.load_alerts(), bf.load_daily()
    minutes, mincov = bf.load_minutes(), bf.load_mincov()
    minutes.update(sp.load_extra_minutes())
    camps = [bf.walk_campaign(a, daily, minutes, mincov) for a in alerts]
    n_first = sum(len(c["fires"]) for c in camps)
    ref = defaultdict(list)
    for r in rerun.read_tsv(REPO / "scripts" / "probes" / "_545rt_rows.tsv"):
        if r["shape_policy"] != POLICY:
            continue
        ref[(r["ticker"], r["ep_date"], r["rung"], r["stop"], r["arm"])].append(r)
    for k in ref:
        ref[k].sort(key=lambda x: int(x["attempt"]))
    chains = rows_checked = drift = 0
    drift_lines = []
    for c in camps:
        if c["enroll_status"] != "ok" or not c["fires"]:
            continue
        ctx = rt._ctx(c, daily)
        for f in c["fires"]:
            for frac in rt.ADR_LADDER:
                for arm in ARMS:
                    attempts, end, meta = run_chain(f["rung"], ctx, f, frac, arm, minutes, date(2026, 8, 31),
                                                    max_attempts=0, mark=False)
                    chains += 1
                    key = (ctx["tkr"], ctx["ep"].isoformat(), f["rung"], rt.kname(frac), arm)
                    rr = ref.get(key, [])
                    if len(rr) != len(attempts):
                        drift += 1
                        drift_lines.append(f"  attempt-count {key}: mine {len(attempts)} vs 09-02 {len(rr)}")
                        continue
                    for a, r in zip(attempts, rr):
                        rows_checked += 1
                        bad = []
                        if a["shape"] != r["shape"]: bad.append("shape")
                        if str(a["fire_date"]) != r["fire_date"]: bad.append("fire_date")
                        if not _cmp(a["fire_minute"], _f(r["fire_minute"])): bad.append("fire_minute")
                        if not _cmp(a["entry"], _f(r["entry"])): bad.append("entry")
                        if not _cmp(a["stop_px"], _f(r["stop_px"])): bad.append("stop_px")
                        if a["status"] != r["status"]: bad.append("status")
                        if (a["outcome"] or "") != (r["outcome"] or ""): bad.append("outcome")
                        if not _cmp(a["r"], _f(r["r"])): bad.append("r")
                        if (str(a["stop_day"]) if a["stop_day"] else "") != (r["stop_day"] or ""): bad.append("stop_day")
                        if not _cmp(a["win_len"], _f(r["win_len"])): bad.append("win_len")
                        if (str(a["win_full"]) if a["win_full"] is not None else "") != (r["win_full"] or ""): bad.append("win_full")
                        if not _cmp(a["win_blind"], _f(r["win_blind"])): bad.append("win_blind")
                        if bad:
                            drift += 1
                            drift_lines.append(f"  {key} att{a['attempt']}: {bad} mine {a['status']}/{a['outcome']}/{a['r']} "
                                               f"vs 09-02 {r['status']}/{r['outcome']}/{r['r']}")
    out.append(f"ANCHOR A — chain logic on the 09-02 files (horizon 08-31, 4 ADR stops x 2 arms, policy either, unlimited): "
               f"{n_first} first fires, {chains} chains, {rows_checked} attempt rows checked, drift {drift}")
    out.extend(drift_lines[:40])

    # (B) first attempt at 09-25, incumbent stop, vs fires.tsv (the rerun's own settlement)
    fires = rerun.load_fires()
    daily2 = rerun.load_daily()
    raw, dropped = rerun.load_minutes_raw()
    minutes2 = rerun.minutes_to_5min(raw)
    camps2 = load_campaigns()
    ctxs = {}
    stat = Counter()
    blines = []
    for f in fires:
        k = (f["ticker"], f["ep_date"])
        if k not in ctxs:
            ctxs[k] = make_ctx(f, daily2)
        ctx = ctxs[k]
        d0 = (f["day0_resolved"], f["day0_post_low"], f["day0_post_high"]) if f["source"] == "lane_recorded" else None
        res = settle_attempt(ctx, minutes2, f["entry"], f["stop"], f["fire_date"], f["fire_minute"], HORIZON, d0_cache=d0, mark=False)
        src = f["source"]
        if res["status"] != "settled" or f["settle_status"] != "settled":
            stat[(src, f"status:{f['settle_status']}->{res['status']}:{res.get('reason', '')}")] += 1
            continue
        ok = (res["outcome"] == f["outcome"] and _cmp(res["realized_r"], f["realized_r"], 1e-4)
              and res["outcome_trail"] == f["outcome_trail"] and _cmp(res["realized_r_trail"], f["realized_r_trail"], 1e-4))
        stat[(src, "match" if ok else "MISMATCH")] += 1
        if not ok and len(blines) < 30:
            blines.append(f"  {src} {f['ticker']} {f['ep_date']} {f['rung']} {f['fire_date']}: mine {res['outcome']}/{res['realized_r']} "
                          f"{res['outcome_trail']}/{res['realized_r_trail']} vs fires.tsv {f['outcome']}/{f['realized_r']} {f['outcome_trail']}/{f['realized_r_trail']}")
    out.append(f"ANCHOR B — first attempt, incumbent stop, horizon 09-25 vs fires.tsv: {dict(stat)}")
    out.extend(blines)
    # ADR$ cross-check: campaigns.tsv vs the real function on the loaded bars
    adr_bad = 0
    for k, c in camps2.items():
        bars = daily2.get(k[0], {})
        epb = bars.get(k[1]) or {}
        adr, _n = compute_ep_adr_dollar([bars[d] for d in sorted(bars)], k[1], epb.get("close"))
        if not _cmp(adr, c["adr_dollar"], 1e-6):
            adr_bad += 1
    out.append(f"ADR$ cross-check: campaigns.tsv vs compute_ep_adr_dollar on the loaded daily bars — {len(camps2)} campaigns, {adr_bad} differ")

    # (C) the horizon mark vs compute_settlement's own s10 checkpoint columns
    cnt = Counter()
    clines = []
    for f in fires:
        if f["source"] != "replay" or f["settle_status"] != "settled":
            continue
        ctx = ctxs[(f["ticker"], f["ep_date"])]
        sessions = _trading_days(f["fire_date"] + timedelta(days=1), HORIZON)
        if len(sessions) < SETTLE_HOLD_SESSIONS:
            continue
        for stop in (f["stop"], f["entry"] - 1.0 * (f["adr_dollar"] or 0)):
            if stop is None or stop >= f["entry"] or stop <= 0:
                continue
            full = settle_attempt(ctx, minutes2, f["entry"], stop, f["fire_date"], f["fire_minute"], HORIZON, mark=False)
            if full["status"] != "settled":
                cnt["full_not_settled"] += 1
                continue
            trunc = settle_attempt(ctx, minutes2, f["entry"], stop, f["fire_date"], f["fire_minute"], sessions[9], mark=True)
            if trunc["status"] == "settled":
                cnt["stopped_or_exited_within_10"] += 1
                continue
            if trunc["status"] != "marked":
                cnt[f"trunc_{trunc['status']}"] += 1
                continue
            ok = _cmp(trunc["realized_r"], full["r_none_s10"], 1e-4) and _cmp(trunc["realized_r_trail"], full["r_trail_s10"], 1e-4)
            cnt["mark_match" if ok else "mark_MISMATCH"] += 1
            if not ok and len(clines) < 20:
                clines.append(f"  {f['ticker']} {f['fire_date']} stop {stop:.4f}: mark {trunc['realized_r']}/{trunc['realized_r_trail']} "
                              f"vs s10 {full['r_none_s10']}/{full['r_trail_s10']}")
    out.append(f"ANCHOR C — mark-at-horizon (sessions truncated to 10) vs compute_settlement r_none_s10 / r_trail_s10: {dict(cnt)}")
    out.extend(clines)
    txt = "\n".join(out) + "\n"
    (HERE / "anchor_out.txt").write_text(txt)
    print(txt)


# ── phase: run ───────────────────────────────────────────────────────────────────────────────────────

def phase_run():
    fires = rerun.load_fires()
    daily = rerun.load_daily()
    raw, dropped = rerun.load_minutes_raw()
    minutes = rerun.minutes_to_5min(raw)
    ctxs = {}
    rows_out, chains_out = [], []
    blind_pairs = set()
    for f in fires:
        k = (f["ticker"], f["ep_date"])
        if k not in ctxs:
            ctxs[k] = make_ctx(f, daily)
        ctx = ctxs[k]
        d0 = (f["day0_resolved"], f["day0_post_low"], f["day0_post_high"]) if f["source"] == "lane_recorded" else None
        for stop_mode in ("incumbent", 0.75, 1.0, 1.5):
            for arm in ARMS:
                attempts, end, meta = run_chain(f["rung"], ctx, f, stop_mode, arm, minutes, HORIZON, d0_cache=d0)
                for d in meta["blind_days"]:
                    blind_pairs.add((f["ticker"], d))
                base = {"ticker": f["ticker"], "ep_date": f["ep_date"].isoformat(), "era": f["era"], "tier": f["tier"],
                        "source": f["source"], "rung": f["rung"], "stop": _stop_label(stop_mode), "arm": arm}
                chains_out.append({**base, "n_attempts": len(attempts), "end": end, "ties": meta["ties"],
                                   "blind": meta["blind"], "missing": meta["missing"]})
                for a in attempts:
                    rows_out.append({**base, **a})
    with open(HERE / "reentry_rows.tsv", "w") as fh:
        fh.write("|".join(ROW_COLS) + "\n")
        for r in rows_out:
            fh.write("|".join("" if r.get(c) is None else str(r.get(c)) for c in ROW_COLS) + "\n")
    with open(HERE / "reentry_chains.tsv", "w") as fh:
        fh.write("|".join(CHAIN_COLS) + "\n")
        for r in chains_out:
            fh.write("|".join("" if r.get(c) is None else str(r.get(c)) for c in CHAIN_COLS) + "\n")
    print(f"{len(fires)} first fires -> {len(chains_out)} chains, {len(rows_out)} attempt rows; "
          f"blind (ticker, day) pairs {len(blind_pairs)}; minute sessions dropped (<{rerun.MIN_MINUTE_BARS} bars) {len(dropped)}")
    print("chain ends:", dict(Counter(c["end"] for c in chains_out)))


# ── phase: report ────────────────────────────────────────────────────────────────────────────────────

def _load_rows():
    rows = rerun.read_tsv(HERE / "reentry_rows.tsv")
    for r in rows:
        r["attempt"] = int(r["attempt"])
        for k in ("entry", "stop_px", "stop_w", "r", "r_gap", "mfe_r", "mae_r"):
            r[k] = _f(r[k])
        r["win_blind"] = int(r["win_blind"]) if r.get("win_blind") else 0
        r["win_full"] = r.get("win_full") == "True"
        r["gap_through"] = r.get("gap_through") == "True"
    chains = rerun.read_tsv(HERE / "reentry_chains.tsv")
    by = defaultdict(list)
    for r in rows:
        by[(r["ticker"], r["ep_date"], r["rung"], r["stop"], r["arm"])].append(r)
    for k in by:
        by[k].sort(key=lambda x: x["attempt"])
    cend = {(c["ticker"], c["ep_date"], c["rung"], c["stop"], c["arm"]): c for c in chains}
    return by, cend


def campaign_cell(attempts, end, cap):
    rows = attempts[:cap]
    cend = "capped" if len(attempts) > cap else end
    floored = [r for r in rows if r["stop_w"] is not None and r["stop_w"] < WIDTH_FLOOR_PCT]
    unsettled = [r for r in rows if r["status"] not in ("settled", "marked")]
    if floored or unsettled:
        return {"readable": False, "why": "floored" if floored else f"abstain:{unsettled[0]['status']}:{unsettled[0]['outcome']}"}
    rg = [r["r_gap"] for r in rows]
    rh = [r["r"] for r in rows]
    cum, worst = 0.0, 0.0
    for x in rg:
        cum += x
        worst = min(worst, cum)
    searched = [r for i, r in enumerate(rows, start=1) if r["outcome"] == "stop" and i < cap]
    # a window counts as searched under this cap only after a stopped attempt i < cap; the chain's own end
    # ("censored_window") applies to the prefix only when the prefix ended before the cap
    return {"readable": True, "total": sum(rg), "total_house": sum(rh), "n_att": len(rows), "worst_cum": worst,
            "all_stops": all(r["outcome"] == "stop" for r in rows), "ge3": sum(rg) >= TAIL_R - _EPS,
            "censored": cend == "censored_window" and len(rows) < cap, "blind": sum(r["win_blind"] for r in searched),
            "open_at_horizon": rows[-1]["outcome"] == "open", "gap_throughs": sum(1 for r in rows if r["gap_through"]),
            "rows": rows, "end": cend}


def _name_worst(cells_by_key):
    """Worst running cumulative gap-charged R per NAME: the name's chains in EP-date order, concatenated."""
    by_name = defaultdict(list)
    for (tkr, ep), c in cells_by_key.items():
        by_name[tkr].append((ep, c["rows"]))
    worst_all, worst_name = 0.0, None
    for tkr, chains in by_name.items():
        cum, w = 0.0, 0.0
        for ep, rows in sorted(chains):
            for r in rows:
                cum += r["r_gap"]
                w = min(w, cum)
        if w < worst_all:
            worst_all, worst_name = w, tkr
    return worst_all, worst_name


def _agg(cells_by_key):
    if not cells_by_key:
        return None
    tot = [c["total"] for c in cells_by_key.values()]
    by_name = defaultdict(float)
    for (tkr, ep), c in cells_by_key.items():
        by_name[tkr] += c["total"]
    ranked = sorted(by_name.items(), key=lambda kv: -kv[1])
    top = ranked[:2]
    drop2 = sum(tot) - sum(v for _, v in top)
    worst, worst_name = _name_worst(cells_by_key)
    months, months_n = defaultdict(float), Counter()
    for (tkr, ep), c in cells_by_key.items():
        months[ep[:7]] += c["total"]
        months_n[ep[:7]] += 1
    att = defaultdict(lambda: [0, 0, 0.0])           # attempt idx -> [fired, stopped, sum r_gap]
    for c in cells_by_key.values():
        for r in c["rows"]:
            a = att[r["attempt"]]
            a[0] += 1; a[1] += int(r["outcome"] == "stop"); a[2] += r["r_gap"]
    return {"n": len(tot), "names": len(by_name), "sum": sum(tot), "sum_house": sum(c["total_house"] for c in cells_by_key.values()),
            "months": {m: f"{v:+.1f}R/n{months_n[m]}" for m, v in sorted(months.items())},
            "top5": [f"{t} {v:+.1f}" for t, v in ranked[:5]], "drop3_sum": sum(tot) - sum(v for _, v in ranked[:3]),
            "attempts_by_idx": {i: {"fired": a[0], "stopped": a[1], "sum": round(a[2], 2)} for i, a in sorted(att.items())},
            "mean": statistics.mean(tot), "median": statistics.median(tot), "win_pct": 100.0 * sum(1 for t in tot if t > 0) / len(tot),
            "ge3": sum(1 for c in cells_by_key.values() if c["ge3"]), "positioned": sum(1 for c in cells_by_key.values() if not c["all_stops"]),
            "attempts": sum(c["n_att"] for c in cells_by_key.values()), "retried": sum(1 for c in cells_by_key.values() if c["n_att"] > 1),
            "drop2_sum": drop2, "drop2_names": [f"{t} {v:+.1f}" for t, v in top], "worst": worst, "worst_name": worst_name,
            "censored": sum(1 for c in cells_by_key.values() if c["censored"]), "blind_names": sum(1 for c in cells_by_key.values() if c["blind"] > 0),
            "blind_sessions": sum(c["blind"] for c in cells_by_key.values()), "open_at_horizon": sum(1 for c in cells_by_key.values() if c["open_at_horizon"]),
            "gap_throughs": sum(c["gap_throughs"] for c in cells_by_key.values())}


def phase_report():
    by, cend = _load_rows()
    runners = load_runners()
    era_of = {}
    for k, rows in by.items():
        era_of[(k[0], k[1])] = rows[0]["era"]
    lines = []
    cells = {}
    unread = {}
    for p in PATTERNS:
        camp_keys = sorted({(k[0], k[1]) for k in by if k[2] == p})
        for s in STOPS:
            for arm in ARMS:
                for cap in CAPS:
                    d, why = {}, Counter()
                    for ck in camp_keys:
                        k = (ck[0], ck[1], p, s, arm)
                        if k not in by:
                            continue
                        res = campaign_cell(by[k], cend[k]["end"], cap)
                        if res["readable"]:
                            d[ck] = res
                        else:
                            why[(era_of[ck], res["why"])] += 1
                    cells[(p, s, cap, arm)] = d
                    unread[(p, s, cap, arm)] = why
    # legs
    verdict = {}
    table = []
    for p in PATTERNS:
        for s in STOPS:
            for arm in ARMS:
                base = cells[(p, "incumbent", 1, arm)]
                lane = cells[(p, "incumbent", 1, "trail")]
                for cap in CAPS:
                    d = cells[(p, s, cap, arm)]
                    A = {k: v for k, v in d.items() if era_of[k] == "A"}
                    B = {k: v for k, v in d.items() if era_of[k] == "B"}
                    aA, aB = _agg(A), _agg(B)
                    pair = {k: v for k, v in A.items() if k in base and era_of[k] == "A"}
                    pair_base = {k: base[k] for k in pair}
                    pA, pB_ = _agg(pair), _agg(pair_base)
                    lane_pair = {k: lane[k] for k in A if k in lane}
                    lpA = _agg({k: A[k] for k in lane_pair}); lpL = _agg(lane_pair)
                    run_fired = [k for k in A if k in runners]
                    run_ge3 = [k for k in run_fired if A[k]["ge3"]]
                    is_base = (s == "incumbent" and cap == 1)
                    legs = {"mean_gt0": aA is not None and aA["mean"] > 0,
                            "drop2_gt0": aA is not None and aA["drop2_sum"] > 0,
                            "beats_base_pairwise": (pA is not None and pB_ is not None and pA["sum"] > pB_["sum"] + _EPS),
                            "worst_within_nominal": (pA is not None and pB_ is not None and pA["worst"] >= pB_["worst"] - (cap - 1) - _EPS),
                            "n_ge_30": aA is not None and aA["n"] >= PASS_N,
                            "era_b_same_sign": (aA is not None and aB is not None and aB["n"] > 0 and (aA["mean"] > 0) == (aB["mean"] > 0))}
                    clears_a = all(legs[x] for x in ("mean_gt0", "drop2_gt0", "beats_base_pairwise", "worst_within_nominal", "n_ge_30")) and not is_base
                    confirmed = clears_a and legs["era_b_same_sign"]
                    rec = {"pattern": p, "stop": s, "tries": cap, "exit": arm, "baseline": is_base,
                           "A": aA, "B": aB, "pair": {"n": pA["n"] if pA else 0, "cell_sum": pA["sum"] if pA else None, "base_sum": pB_["sum"] if pB_ else None,
                                                      "cell_worst": pA["worst"] if pA else None, "base_worst": pB_["worst"] if pB_ else None},
                           "lane_pair": {"n": lpA["n"] if lpA else 0, "cell_sum": lpA["sum"] if lpA else None, "lane_sum": lpL["sum"] if lpL else None},
                           "runners_fired": len(run_fired), "runners_ge3": len(run_ge3), "runner_names_ge3": sorted(k[0] for k in run_ge3),
                           "unreadable": {f"{e}:{w}": n for (e, w), n in unread[(p, s, cap, arm)].items()},
                           "legs": legs, "clears_era_a": clears_a, "confirmed": confirmed}
                    table.append(rec)
    draws = [t for t in table if not t["baseline"]]
    clearing = [t for t in draws if t["clears_era_a"]]
    confirmed = [t for t in draws if t["confirmed"]]
    outcome = "(i)" if confirmed else ("(ii)" if clearing else "(iii)")
    verdict = {"cells": N_CELLS, "baselines": N_BASELINES, "draws": len(draws), "noise_max": NOISE_MAX, "family_min": FAMILY_MIN,
               "clearing_era_a": len(clearing), "confirmed": len(confirmed), "declared_outcome": outcome,
               "mean_gt0_A": sum(1 for t in draws if t["legs"]["mean_gt0"]), "drop2_gt0_A": sum(1 for t in draws if t["legs"]["drop2_gt0"]),
               "beats_base": sum(1 for t in draws if t["legs"]["beats_base_pairwise"]),
               "mean_gt0_B": sum(1 for t in draws if t["B"] is not None and t["B"]["mean"] > 0),
               "clearing_cells": [f"{t['pattern']}/{t['stop']}/x{t['tries']}/{t['exit']}" for t in clearing],
               "confirmed_cells": [f"{t['pattern']}/{t['stop']}/x{t['tries']}/{t['exit']}" for t in confirmed]}
    lines.append(f"CELLS {N_CELLS} = {N_BASELINES} baselines + {len(draws)} draws; noise band <= {NOISE_MAX} clearing ERA A, family >= {FAMILY_MIN}")
    lines.append(f"VERDICT: clearing ERA A {len(clearing)} of {len(draws)}; confirmed by ERA B {len(confirmed)}; declared outcome {outcome}")
    lines.append(f"   legs alone (draws): mean>0 ERA A {verdict['mean_gt0_A']} · drop-2 > 0 {verdict['drop2_gt0_A']} · beats baseline {verdict['beats_base']} · ERA B mean>0 {verdict['mean_gt0_B']}")
    for t in clearing:
        lines.append(f"   clears ERA A: {t['pattern']}/{t['stop']}/x{t['tries']}/{t['exit']} A mean {t['A']['mean']:+.2f} n {t['A']['n']} drop2 {t['A']['drop2_sum']:+.1f} "
                     f"drop3 {t['A']['drop3_sum']:+.1f} top5 {t['A']['top5']} months {t['A']['months']} | attempts {t['A']['attempts_by_idx']} | "
                     f"B n {t['B']['n'] if t['B'] else 0} mean {t['B']['mean'] if t['B'] else None} sum {t['B']['sum'] if t['B'] else None} "
                     f"B attempts {t['B']['attempts_by_idx'] if t['B'] else None} B censored {t['B']['censored'] if t['B'] else None} blind names {t['B']['blind_names'] if t['B'] else None} "
                     f"open {t['B']['open_at_horizon'] if t['B'] else None}")

    def fa(a, key, fmt="{:+.2f}"):
        return "—" if a is None else fmt.format(a[key])

    for p in PATTERNS:
        lines.append(f"\n{'=' * 150}\n== {p} ==\n{'=' * 150}")
        hdr = (f"{'stop':10s}{'x':3s}{'exit':6s}| {'nA':>3s} {'names':>5s} {'meanA':>7s} {'sumA':>7s} {'house':>7s} {'drop2':>7s} {'worst':>6s} "
               f"{'pair n':>6s} {'cell':>7s} {'base':>7s} {'bw':>5s} | {'>=3R':>4s} {'run':>5s} {'pos':>4s} {'att':>4s} {'cens':>4s} {'blind':>5s} {'open':>4s} {'gapT':>4s} "
               f"| {'nB':>3s} {'meanB':>6s} {'sumB':>6s} {'censB':>5s} {'blindB':>6s} | {'unreadable A/B':22s} | legs")
        lines.append(hdr)
        for t in [t for t in table if t["pattern"] == p]:
            A, B = t["A"], t["B"]
            legs = "".join(("1" if t["legs"][x] else "0") for x in ("mean_gt0", "drop2_gt0", "beats_base_pairwise", "worst_within_nominal", "n_ge_30", "era_b_same_sign"))
            ua = sum(n for k, n in t["unreadable"].items() if k.startswith("A:"))
            ub = sum(n for k, n in t["unreadable"].items() if k.startswith("B:"))
            lines.append(f"{t['stop']:10s}{t['tries']:<3d}{t['exit']:6s}| {fa(A, 'n', '{:d}'):>3s} {fa(A, 'names', '{:d}'):>5s} {fa(A, 'mean'):>7s} {fa(A, 'sum', '{:+.1f}'):>7s} "
                         f"{fa(A, 'sum_house', '{:+.1f}'):>7s} {fa(A, 'drop2_sum', '{:+.1f}'):>7s} {fa(A, 'worst', '{:+.1f}'):>6s} "
                         f"{t['pair']['n']:>6d} {('—' if t['pair']['cell_sum'] is None else format(t['pair']['cell_sum'], '+.1f')):>7s} "
                         f"{('—' if t['pair']['base_sum'] is None else format(t['pair']['base_sum'], '+.1f')):>7s} "
                         f"{('—' if t['pair']['base_worst'] is None else format(t['pair']['base_worst'], '+.1f')):>5s} | "
                         f"{fa(A, 'ge3', '{:d}'):>4s} {t['runners_ge3']}/{t['runners_fired']:<3d} {fa(A, 'positioned', '{:d}'):>4s} {fa(A, 'attempts', '{:d}'):>4s} "
                         f"{fa(A, 'censored', '{:d}'):>4s} {fa(A, 'blind_names', '{:d}'):>5s} {fa(A, 'open_at_horizon', '{:d}'):>4s} {fa(A, 'gap_throughs', '{:d}'):>4s} "
                         f"| {fa(B, 'n', '{:d}'):>3s} {fa(B, 'mean'):>6s} {fa(B, 'sum', '{:+.1f}'):>6s} {fa(B, 'censored', '{:d}'):>5s} {fa(B, 'blind_names', '{:d}'):>6s} "
                         f"| {str(ua) + '/' + str(ub):22s} | {legs}{' BASE' if t['baseline'] else ''}{' CLEARS-A' if t['clears_era_a'] else ''}{' CONFIRMED' if t['confirmed'] else ''}")
        # drop-2 names on the best cells
        best = sorted([t for t in table if t["pattern"] == p and t["A"] is not None], key=lambda t: -t["A"]["sum"])[:3]
        for t in best:
            lines.append(f"   best by ERA A total: {t['stop']}/x{t['tries']}/{t['exit']} sum {t['A']['sum']:+.1f} (n {t['A']['n']}); top-2 names {t['A']['drop2_names']} -> drop-2 {t['A']['drop2_sum']:+.1f}; "
                         f"worst name {t['A']['worst_name']} {t['A']['worst']:+.1f}; runners >= 3R {t['runner_names_ge3']}; ERA B n {t['B']['n'] if t['B'] else 0} mean {fa(t['B'], 'mean')}")
    # ERA B: the lane's horizon and abstentions, in words
    lines.append("\nERA B per pattern (the incumbent x1 x trail cell): readable n, censored windows, blind, unreadable")
    for p in PATTERNS:
        t = next(t for t in table if t["pattern"] == p and t["stop"] == "incumbent" and t["tries"] == 1 and t["exit"] == "trail")
        t4 = next(t for t in table if t["pattern"] == p and t["stop"] == "adr_100" and t["tries"] == 4 and t["exit"] == "trail")
        lines.append(f"   {p:20s} x1: n_B {t['B']['n'] if t['B'] else 0} unreadable {t['unreadable']} | adr_100 x4: n_B {t4['B']['n'] if t4['B'] else 0} "
                     f"censored {t4['B']['censored'] if t4['B'] else 0} blind names {t4['B']['blind_names'] if t4['B'] else 0} open-at-horizon {t4['B']['open_at_horizon'] if t4['B'] else 0} unreadable {t4['unreadable']}")

    # TEAM hand-walk in the best-by-ERA-A-total cell of each pattern
    lines.append(f"\nTEAM {TEAM[1]} — hand-walk in each pattern's best-by-ERA-A-total cell")
    team = {}
    for p in PATTERNS:
        best = max((t for t in table if t["pattern"] == p and t["A"] is not None), key=lambda t: t["A"]["sum"])
        k = (TEAM[0], TEAM[1].isoformat(), p, best["stop"], best["exit"])
        if k not in by:
            lines.append(f"   {p}: best cell {best['stop']}/x{best['tries']}/{best['exit']} — TEAM did not fire on this pattern")
            team[p] = None
            continue
        rows = by[k][:best["tries"]]
        cell = campaign_cell(by[k], cend[k]["end"], best["tries"])
        lines.append(f"   {p}: best cell {best['stop']}/x{best['tries']}/{best['exit']} — TEAM total {cell.get('total', float('nan')):+.2f}R over {len(rows)} attempt(s), end {cell.get('end')}")
        for r in rows:
            lines.append(f"      att{r['attempt']} [{r['shape']}] {r['fire_date']} min {r['fire_minute'] or 'daily'} entry {r['entry']:.2f} stop {r['stop_px']:.2f} ({r['stop_w']:.2f}%) "
                         f"-> {r['outcome']} {r['r']:+.2f}R (gap-charged {r['r_gap']:+.2f}) stop_day {r['stop_day'] or '—'} marked_at {r['marked_at'] or '—'} mfe {r['mfe_r']}")
        team[p] = {"cell": f"{best['stop']}/x{best['tries']}/{best['exit']}", "total": cell.get("total"), "attempts": [
            {k2: r[k2] for k2 in ("attempt", "shape", "fire_date", "fire_minute", "entry", "stop_px", "stop_w", "outcome", "r", "r_gap", "stop_day", "marked_at")} for r in rows]}

    txt = "\n".join(lines) + "\n"
    (HERE / "reentry_report.txt").write_text(txt)
    print(txt)
    with open(HERE / "reentry_cells.tsv", "w") as fh:
        cols = ["pattern", "stop", "tries", "exit", "baseline", "n_A", "names_A", "mean_A", "sum_A", "sum_house_A", "drop2_A", "drop2_names", "worst_A", "worst_name_A",
                "pair_n", "pair_cell_sum", "pair_base_sum", "pair_cell_worst", "pair_base_worst", "lane_pair_n", "lane_pair_cell", "lane_pair_lane",
                "ge3_A", "runners_ge3", "runners_fired", "positioned_A", "attempts_A", "retried_A", "censored_A", "blind_names_A", "open_A", "gap_throughs_A",
                "n_B", "mean_B", "sum_B", "censored_B", "blind_names_B", "open_B", "unreadable", "legs", "clears_era_a", "confirmed"]
        fh.write("\t".join(cols) + "\n")
        for t in table:
            A, B = t["A"], t["B"]
            g = lambda a, k: "" if a is None else a[k]
            fh.write("\t".join(str(x) for x in (
                t["pattern"], t["stop"], t["tries"], t["exit"], t["baseline"], g(A, "n"), g(A, "names"), g(A, "mean"), g(A, "sum"), g(A, "sum_house"), g(A, "drop2_sum"),
                ";".join(A["drop2_names"]) if A else "", g(A, "worst"), g(A, "worst_name"), t["pair"]["n"], t["pair"]["cell_sum"], t["pair"]["base_sum"],
                t["pair"]["cell_worst"], t["pair"]["base_worst"], t["lane_pair"]["n"], t["lane_pair"]["cell_sum"], t["lane_pair"]["lane_sum"],
                g(A, "ge3"), t["runners_ge3"], t["runners_fired"], g(A, "positioned"), g(A, "attempts"), g(A, "retried"), g(A, "censored"), g(A, "blind_names"), g(A, "open_at_horizon"), g(A, "gap_throughs"),
                g(B, "n"), g(B, "mean"), g(B, "sum"), g(B, "censored"), g(B, "blind_names"), g(B, "open_at_horizon"), json.dumps(t["unreadable"]),
                "".join("1" if t["legs"][x] else "0" for x in ("mean_gt0", "drop2_gt0", "beats_base_pairwise", "worst_within_nominal", "n_ge_30", "era_b_same_sign")),
                t["clears_era_a"], t["confirmed"])) + "\n")
    (HERE / "reentry_summary.json").write_text(json.dumps({"verdict": verdict, "team": team, "cells": table}, indent=1, default=str))
    print("wrote reentry_cells.tsv, reentry_report.txt, reentry_summary.json")


if __name__ == "__main__":
    {"gate": phase_gate, "anchor": phase_anchor, "run": phase_run, "report": phase_report}[sys.argv[1]]()
