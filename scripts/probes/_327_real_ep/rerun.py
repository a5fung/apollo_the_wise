"""#327 — the delayed-entry lane on the EPs our system actually caught: the RIGHT-population rerun.
2026-09-26 (Saturday build slot). $0, read-only prod pulls captured once (extract_1.sh, extract_2.sh),
then worked entirely from files. No toggle, no table, no deploy, no PLAN.md line.

WHY THIS RUN EXISTS. Three analyses earlier today (327_exit_determination_2026-09-26.md, its addendum,
327_leaders_ep_management_2026-09-26.md) measured the WRONG POPULATION: 98.5% of their fires were on
gappers the EP scan never alerted (the lane's voided first week). Operator: "Run it right this time",
"I don't want any mistakes". Operator ruling 2026-09-01 (commit e77436c2): delayed entry is "a trading
entry/exit tactic" on "any real EPs our system caught".

═══════════════════════════════ STEP 0 — THE POPULATION GATE ═══════════════════════════════
Live-source `mi_ep_alerts` 2026-05-01 → 2026-09-11, one campaign per (ticker, alert_date) (gate.sql;
output gate_out.txt, pulled 2026-09-27T00:06:58Z). The EP rules changed inside the window (#533 score
redesign 08-22; gap floor 10→9 on 08-19; extension cap 50→75 on 08-22, reverted 08-29; real-time gap
authority 08-27), so the population is split into two ERAS by alert_date and each was required to
reproduce exactly. IT DID:
    ERA A (alert_date < 2026-08-22): 261 campaigns · 243 names · HIGH 184 / MODERATE 66 / other 11 ·
           alert dates 05-11 → 08-21 · 0 priced under $5 · TEAM 08-07, MRNA 08-19, PLTR 08-04,
           HTFL 08-14 present
    ERA B (alert_date ≥ 2026-08-22): 16 campaigns · 16 names · HIGH 14 / MODERATE 2 ·
           alert dates 08-27 → 09-08 · 0 priced under $5
    ALL: 277 campaigns, 256 names. (The task text's "267" is the May–Aug count of the 09-01 backfill;
    the 05-01 → 09-11 population is 277. Every table below states its n from these 277.)
OPERATOR RULING 2026-09-26 (option 1): use the EPs as the system caught them, test the eras separately,
trust only an answer that holds in BOTH; if the eras disagree, report it and stop there.
`mi_delayed_entry_trigger`'s live rows are NEVER the population (they include the voided cohort) — the
lane's four patterns are REPLAYED on the 277 campaigns from stored bars, exactly as
delayed_entry_backfill_2026-09-01.md did, through that probe's own walker (imported, horizon patched).

═══════════════════════════════ PRE-REGISTRATION (before any A–E number) ═══════════════════════════════
INSTRUMENT. `scripts/probes/_562_backfill_replay.py`'s `walk_campaign` — the lane's own pure functions
(`session_needs_minutes`, `evaluate_session_minute/daily`, `evaluate_session_620`, `compute_settlement`,
`to_rth_5min`, `compute_ep_adr_dollar`, the rung constants), first attempts only (re-entry shapes NOT
replayed — stated as a limit, as on 09-01). Its horizon constant is patched to 2026-09-25 (the last
daily bar). THE ABSTAIN RULE holds: a minute-resolution decision with no minute bars folds daily facts
and never fires at minute grade. New here: a session with FEWER THAN 100 stored RTH 1-min bars is treated
as MISSING (66 of 5,173 window sessions — EP-day scan snapshots of one bar; evaluating a day on one
bucket would corrupt the state the next sessions inherit). Minute bars were checked against the adjusted
daily table on every full-coverage session: 0 of 4,252 depart by more than 2% (max 1.7%, closing-auction
noise), so NO rescale is applied — this population has no post-EP splits.
ANCHORS, printed before any result: (1) the 09-01 backfill's 602 first-attempt fires reproduce
row-for-row from its own files (phase `reproduce`); (2) the same 267 campaigns on TODAY's pull with the
08-31 horizon, differences classified; (3) the live lane's recorded FIRST-attempt fires on the 16 ERA B
campaigns (it has enrolled only EP alerts since 09-01; `_327_block5/trigger.csv`, pulled today) are
compared to this replay's ERA B fires by (rung, fire date, entry, stop) — the one place the lane's own
rows are a check on the exact population; (4) the grid's incumbent cell (incumbent stop · no target ·
trail max(SMA10,SMA20)) equals the REAL `compute_settlement` on the same inputs at s10 / s20.
CHECKPOINT. K = 10 sessions after the fire is PRIMARY (every campaign has ≥ 10 later sessions by
09-25; the 09-08 alerts have 13). Population per cell = fires with ≥ K sessions elapsed by 09-25, never
settlement status; open positions are marked at the session-K close. K = 20 is reported beside it (ERA B
cannot reach it — said plainly). Width floor: a fire whose stop is under 0.5% wide in the cell's own stop
units is counted, not scored (Block 5's rule); unfloored n beside it.
ERA SPLIT of every table: ERA A / ERA B by the campaign's alert_date, pooled beside.

A. ENTRY EDGE per pattern vs a matched same-window NON-FIRE control (Block 5 P2's method, imported):
   fire entered at its recorded entry (the 5-min close for a minute fire; the LEVEL for a daily-grade
   `ep_high_break`), stop = entry − 1×ADR$, target = entry + 2×ADR$ (ADR$ = the real
   `compute_ep_adr_dollar`, 20 sessions before the EP), first passage over day 0 (post-fire 5-min bars;
   a level fire folds its whole day) + sessions 1..K; both straddle bounds (pess = stop first on a bar
   holding both, opt = target first). Control = every non-fire session inside the 20-session window of
   each campaign where THAT pattern fired, entered at the session's close, same clock. Beside the bar:
   the fire entered at the fire session's CLOSE (like-for-like with the control) and the FILLABLE entry
   (max(level, fire-day open) for level fires). Reported: rate reaching +2ADR before −1ADR at s10, gap
   in points, n both sides, names, drop-best-NAME, per era.
B. THE GRID. Block 5 P3's 7 stops (incumbent · entry − {0.25, 0.5, 0.75, 1.0, 1.5}×ADR$ · prior-session
   low) × 7 targets (none · 1R · 2R · 3R · 1×ADR$ · 2×ADR$ · 3×ADR$) × 12 exits (none · trail SMA10 ·
   trail SMA20 · trail max(SMA10,SMA20) [the incumbent arm] · time s3 · s5 · s10 · his marked-chart
   exits sma21_2x · ema23_2x · sma50_1x · ema65_1x · hv21_50_noreclaim2) = 588 cells, walked by P3's own
   `first_passages` / `exit_sessions` / `cell_r` (imported; definitions in p3_grid.py's docstring).
   PLUS the EP-style management arms of the leaders run (P6, imported `walk_mgmt` / `run_m1`): partial
   1/3 at +2R / +3R × breakeven at +1R / +2R / after the partial × remainder trailed on SMA10 / SMA20 /
   held to s20 (18 arms) + the LIVE MAGNA53 stack as of each fire date via
   `rule_eras.exit_rules_as_of(fire_date, "magna53")` → `live_fill_counterfactuals.stack_walk_inputs` →
   `walk_arm(harvest="live_ladder")` in P6's two declared ORB-R frames (M1_orb2: ORB-R = half the stop
   distance; M1_orb1: the whole stop distance) + the SAME stack as it stands TODAY (2026-09-25, era D:
   +8R partial, breakeven armed at +3R) applied to every fire (M1t_orb2 / M1t_orb1) — 22 arms × 3 stops
   (incumbent · 0.5×ADR$ · 1.0×ADR$) = 66 cells. Management cells are GAP-CHARGED (a session that opens
   below the resting stop fills at the open); grid cells carry a gap-charged R beside the house −1.00R.
   TOTAL DRAWS = 588 + 66 = 654 on the RECORDED entry at K = 10 (the bar). The fillable entry and K = 20
   are reported beside, never as extra draws. Noise band scaled from Block 5's "1–3 of 294": ≤ 7 of 654
   clearing is noise; ≥ 55 is a family.
C. PASS BAR per cell, tail first (his frame: "catch big winners while limiting losses"), judged on ERA A:
   mean R > 0 · kept ≥ 3R rate ≥ 3 × THIS POPULATION'S OWN INCUMBENT RATE (the lane's arm: incumbent
   stop · no target · trail max(SMA10,SMA20) at s10 on ERA A — measured and stated before any cell is
   read; the 3.0% absolute floor of P3/P6 is reported beside it, never substituted) · average loss
   (mean R over losers, gap-charged) no worse than −1.0R · mean R > 0 after dropping the single best NAME
   by summed R · ERA RULE: ERA B (16 campaigns) is too thin for the full bar and can only confirm
   DIRECTION — a cell counts only if ERA B's mean R has the same sign as ERA A's, with ERA B's n stated;
   a cell with ZERO ERA B fires is NOT confirmed · pooled n ≥ 150 fires over ≥ 60 names. The clearing
   COUNT is judged against the 654 draws before any cell is named. Declared outcomes: (i) cells clear
   ERA A and ERA B confirms them → named, fork on them; (ii) cells clear ERA A and NONE is confirmed →
   verdict "eras disagree — re-score under today's rules", stop there; (iii) zero cells clear ERA A →
   the eras agree on a null, fork on the lane.
D. BIG WINNERS: of the campaigns with EP date ≤ 2026-09-04 (15 later sessions exist), those whose highest
   high within 15 sessions ≥ +50% over the EP-day close AND whose session-15 close held ≥ +30%; did the
   patterns fire on them (which, at what session); for every arm × stop, the runner fires KEPT ≥ 3R
   (at s20, or the last available mark) against the incumbent arm, and the same arm's mean R on every
   NON-runner fire against the incumbent's — "did we keep the winners, and what did it cost".
E. NAMED CASES: TEAM 2026-08-07 (live: in 147.13 at 09:31 ET, stopped 143.14 at 09:43 ET the same day —
   every lane fire is after our stop BY CONSTRUCTION, the lane starts the session after the EP day) and
   MRNA 2026-08-19 (live: in 120.75, partial 1 of 4 at 138.46 at 09:55 ET the same day, trailed out at
   145.11 on 09-03 09:32 ET = session 11): each first-attempt fire, its date / minute / entry / stop,
   before or after our exit, and what the incumbent arms, the live stack (both frames, as-of and today)
   and the 18 management arms would have done at s10 / s20 and marked at 09-25.

ERA B COVERAGE — found while sizing, declared here, before any outcome. `mi_intraday_bars` holds NO September
minute bars for 10 of the 16 ERA B campaigns (AGX, ALAB, CHRN, DG, ERO, IONQ, QCOM, ROIV, SNOW, VEEV: 0–1 of
their 13–20 forward sessions covered), so the replay cannot see their minute-grade fires — anchor (3) found 17 of
the lane's 37 recorded ERA B first fires MISSING and one (IONQ ep_low_reclaim) fired 10 sessions late on the first
covered session. Six campaigns are fully covered (CRWD, HOOD, OKTA, PHVS, SEI, SOLS) and there the replay matches
the lane's 19 recorded first fires exactly (19 of 19 by rung, date, entry, stop). PRE-REGISTERED HANDLING: a
campaign with fewer than half its forward sessions minute-covered is UNCOVERED; on an uncovered ERA B campaign
the lane's OWN recorded first-attempt fires (`_327_block5/trigger.csv`, `reentry_shape = first`; the lane has
enrolled only EP alerts since 09-01, so on these 16 campaigns its rows ARE the right population) replace the
replay's fires — 23 rows; their day 0 = real bars where the session is covered, else the row's cached
`day0_resolved / day0_post_low / day0_post_high` through the production `day0_pseudo_bars` (Block 5 P3's exact
fallback), else ABSTAIN when the day low reached the cell's stop (never a guess). The replay-only ERA B read (the
six covered campaigns) is reported beside the combined one, and the lane's recorded settlement on all 37 ERA B
first fires (its own incumbent arm, no walk) is a third, independent direction read. Nine late ERA A campaigns
(alerts 07-10 and 08-17 → 08-21) sit under the same coverage line for their September sessions; they predate the
lane, stay as replay (their first fires fell on covered August sessions) and are named in the doc.

POPULATION COUNTS seen while sizing (phase `replay`, counts only — no outcome read before this file and the
doc's Method section were committed):
    277 campaigns walked, 0 unenrollable; 632 first-attempt fires = 609 replayed + 23 lane-recorded;
    sessions abstained 117 of 5,593 (ERA A 41; ERA B 76); minute sessions dropped (< 100 bars) 67.
    ERA A: 261 campaigns, family fired on 252; 595 fires — ep_low_reclaim 202 (189 names; 201 with ≥ 10
           sessions elapsed, 199 with ≥ 20) · ep_close_reclaim 142 (135; 141 / 140) · ep_high_break 48 (47;
           48 / 48; 33 daily-grade level fires, 15 minute-grade) · ep_close_620_prox 203 (194; 203 / 201).
    ERA B: 16 campaigns, family fired on 15; 37 fires — ep_low_reclaim 13 (11 with ≥ 10 elapsed; 9 lane-recorded)
           · ep_close_reclaim 9 (9; 5) · ep_high_break 2 (2; 1) · ep_close_620_prox 13 (11; 8). ZERO ERA B fires
           reach 20 sessions by 09-25 — K = 20 is an ERA A-only read.
    Anchors: (1) 602 of 602; (2) 594 of 602 row-for-row on today's pull, the 8 differences = 7 ep_close_620_prox
           fires re-timed 0–4 sessions because their 6/20-MACD warm-up in the 09-01 run included a one-bar EP-day
           snapshot that the < 100-bar rule now drops (entries within 0.1–2.3%), + 1 ep_low_reclaim (HGTY) moved
           one session by the same rule; (3) 19 of 19 on covered ERA B campaigns, 17 missing + 1 late on
           uncovered ones (handled above).

Usage:
    python3 rerun.py reproduce   # anchors (1) + (2)
    python3 rerun.py replay      # fires.tsv / campaigns.tsv + anchor (3), counts only
    python3 rerun.py analyze     # A–E → summary.json, cells.tsv, events.csv (gitignored)
"""
from __future__ import annotations

import csv
import gzip
import json
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts" / "probes"))
sys.path.insert(0, str(REPO / "scripts" / "probes" / "_327_block5"))

import _562_backfill_replay as bf                                   # noqa: E402  the 09-01 walker
from agents.market_intelligence.delayed_entry_shadow import (       # noqa: E402  real code
    compute_ep_adr_dollar, compute_settlement, sma_trail_line, to_rth_5min, _trading_days,
)
from agents.market_intelligence.rule_eras import exit_era_label, exit_rules_as_of   # noqa: E402
from agents.market_intelligence.live_fill_counterfactuals import PRIOR_CLOSES_CAL_DAYS  # noqa: E402
import p2_probe                                                     # noqa: E402  first_passage / at_checkpoint
import p3_grid                                                      # noqa: E402  the grid walkers
import p6_leaders_mgmt as p6                                        # noqa: E402  management walkers

_ET = ZoneInfo("America/New_York")
LAST_SESSION = date(2026, 9, 25)
TODAY_RULES_DATE = date(2026, 9, 25)
WINDOW = 20
CHECKPOINTS = (10, 20)
PRIMARY_K = 10
WIDTH_FLOOR_PCT = 0.5
TAIL_R = 3.0
_EPS = 1e-9
MIN_MINUTE_BARS = 100
ERA_SPLIT = date(2026, 8, 22)
PATTERNS = ("ep_low_reclaim", "ep_close_reclaim", "ep_high_break", "ep_close_620_prox")
STOPS, TARGETS, EXITS = p3_grid.STOPS, p3_grid.TARGETS, p3_grid.EXITS
ADR_MULT = p3_grid.ADR_MULT
MGMT_STOPS = ("incumbent", "adr_050", "adr_100")
M1_ARMS = ("M1_orb2", "M1_orb1", "M1t_orb2", "M1t_orb1")
GRID_ARMS = p6.GRID_ARMS
MGMT_ARMS = M1_ARMS + GRID_ARMS
CONVENTIONS = ("recorded", "fillable")
N_GRID = len(STOPS) * len(TARGETS) * len(EXITS)
N_MGMT = len(MGMT_STOPS) * len(MGMT_ARMS)
N_DRAWS = N_GRID + N_MGMT
PASS = {"tail_abs_pct": 3.0, "tail_mult": 3.0, "avg_loss": -1.0, "n": 150, "names": 60}
RUNNER = {"ep_max": date(2026, 9, 4), "sessions": 15, "gain": 1.5, "hold": 1.3}
NAMED = (("TEAM", date(2026, 8, 7)), ("MRNA", date(2026, 8, 19)))
NAMED_EXIT = {("TEAM", date(2026, 8, 7)): (date(2026, 8, 7), 9 * 60 + 43),
              ("MRNA", date(2026, 8, 19)): (date(2026, 9, 3), 9 * 60 + 32)}

STOP, TARGET, EXIT, OPEN, ABSTAIN, KILLED = "stop", "target", "exit", "open", "abstain", "killed"


def _f(v):
    if v in (None, "", "\\N"):
        return None
    try:
        return float(v)
    except ValueError:
        return None


def read_tsv(path, gz=False):
    opener = (lambda: gzip.open(path, "rt")) if gz else (lambda: open(path))
    with opener() as fh:
        rows = list(csv.reader(fh, delimiter="|"))
    hdr = rows[0]
    return [dict(zip(hdr, r)) for r in rows[1:] if len(r) == len(hdr)]


# ── loaders (the new pull) ────────────────────────────────────────────────────────────

def load_alerts():
    out = []
    for r in read_tsv(HERE / "alerts.tsv"):
        out.append({"ticker": r["ticker"], "ep_date": date.fromisoformat(r["alert_date"]),
                    "tier": r["score_tier"] or "none", "ep_score": _f(r["ep_score"]),
                    "gap_pct": _f(r["gap_pct"]), "catalyst_grade": r["catalyst_quality"] or None,
                    "era": r["era"], "prior_close": _f(r["prior_close"])})
    return out


def load_daily():
    by = defaultdict(dict)
    for r in read_tsv(HERE / "daily.tsv"):
        d = date.fromisoformat(r["trade_date"])
        by[r["ticker"]][d] = {"trade_date": d, "open_price": _f(r["open_price"]),
                              "high_price": _f(r["high_price"]), "low_price": _f(r["low_price"]),
                              "close": _f(r["close"]), "volume": _f(r["volume"])}
    return by


def load_minutes_raw():
    """(ticker, day) -> raw 1-min bars {t, o, h, l, c, v} (RTH only), sessions under
    MIN_MINUTE_BARS dropped (treated as missing — the pre-registered rule)."""
    raw = defaultdict(list)
    for r in read_tsv(HERE / "minute.tsv.gz", gz=True):
        t = int(float(r["t_ms"]))
        et = datetime.fromtimestamp(t / 1000, tz=timezone.utc).astimezone(_ET)
        m = et.hour * 60 + et.minute
        if not (570 <= m < 960):
            continue
        raw[(r["ticker"], date.fromisoformat(r["d"]))].append(
            {"t": t, "m": m, "o": float(r["o"]), "h": float(r["h"]), "l": float(r["l"]),
             "c": float(r["c"]), "v": _f(r["v"]) or 0})
    dropped = {k: len(v) for k, v in raw.items() if len(v) < MIN_MINUTE_BARS}
    for k in dropped:
        del raw[k]
    for v in raw.values():
        v.sort(key=lambda b: b["t"])
    return raw, dropped


def minutes_to_5min(raw):
    return {(t, d): to_rth_5min(bars, d) for (t, d), bars in raw.items()}


# ── phase: reproduce the 09-01 backfill ───────────────────────────────────────────────

def _fire_key(f, tkr=None, ep=None):
    return (tkr or f["ticker"], str(ep or f["ep_date"]), f["rung"], str(f["fire_date"]),
            round(float(f["entry"]), 4), round(float(f["stop"]), 4))


def phase_reproduce():
    out = {}
    # (1) the backfill's own files + its own walker, horizon 08-31
    bf.LAST_DATA_DAY = date(2026, 8, 31)
    alerts, daily = bf.load_alerts(), bf.load_daily()
    minutes, mincov = bf.load_minutes(), bf.load_mincov()
    camps = [bf.walk_campaign(a, daily, minutes, mincov) for a in alerts]
    mine = Counter(_fire_key(f, c["ticker"], c["ep_date"]) for c in camps for f in c["fires"])
    rec = Counter(_fire_key(t) for t in bf.read_tsv("_562bf_triggers.tsv"))
    n_mine, n_rec = sum(mine.values()), sum(rec.values())
    common = sum((mine & rec).values())
    out["anchor1_old_files"] = {"fires_replayed": n_mine, "fires_recorded_09_01": n_rec,
                               "row_for_row_match": common, "campaigns": len(camps)}
    print(f"ANCHOR 1 — 09-01 backfill on its own files: {n_mine} fires replayed vs {n_rec} recorded; "
          f"{common} match row-for-row (ticker, EP date, rung, fire date, entry, stop)")
    old_fires = {c["ticker"] + "|" + str(c["ep_date"]): {_fire_key(f, c["ticker"], c["ep_date"]) for f in c["fires"]}
                 for c in camps}
    # (2) the same 267 campaigns on TODAY's pull, horizon 08-31
    new_alerts = [a for a in load_alerts() if a["ep_date"] <= date(2026, 8, 31)]
    ndaily = load_daily()
    raw, dropped = load_minutes_raw()
    nmin = minutes_to_5min(raw)
    camps2 = [bf.walk_campaign(a, ndaily, nmin, set()) for a in new_alerts]
    mine2 = Counter(_fire_key(f, c["ticker"], c["ep_date"]) for c in camps2 for f in c["fires"])
    common2 = sum((mine2 & rec).values())
    n2 = sum(mine2.values())
    # classify the differences by campaign
    only_old = rec - mine2
    only_new = mine2 - rec
    by_reason = Counter()
    detail = []
    for k in list(only_old) + list(only_new):
        tkr, ep = k[0], date.fromisoformat(k[1])
        side = "only_09_01" if k in only_old else "only_today"
        # was the fire session's minute coverage different between the two pulls?
        fd = date.fromisoformat(k[3])
        old_has = (tkr, fd) in minutes
        new_has = (tkr, fd) in nmin
        if old_has != new_has:
            why = "minute_coverage_differs" + ("_dropped_lt100" if (tkr, fd) in dropped else "")
        else:
            ob = daily.get(tkr, {}).get(fd, {}); nb = ndaily.get(tkr, {}).get(fd, {})
            why = "daily_bar_differs" if (ob.get("close") != nb.get("close") or ob.get("low_price") != nb.get("low_price")
                                          or ob.get("high_price") != nb.get("high_price")) else "other"
        by_reason[(side, why)] += 1
        detail.append((side, why) + k)
    out["anchor2_today_pull_267"] = {"fires_replayed": n2, "row_for_row_match": common2,
                                     "only_09_01": sum(only_old.values()), "only_today": sum(only_new.values()),
                                     "reasons": {f"{s}:{w}": n for (s, w), n in by_reason.items()},
                                     "detail": sorted(detail)[:60],
                                     "sessions_dropped_lt100_bars": len(dropped)}
    print(f"ANCHOR 2 — same 267 campaigns on today's pull (horizon 08-31): {n2} fires; {common2} match the 09-01 rows; "
          f"only-09-01 {sum(only_old.values())}, only-today {sum(only_new.values())}; reasons {dict(by_reason)}")
    for d in sorted(detail)[:40]:
        print("   ", d)
    (HERE / "reproduce_summary.json").write_text(json.dumps(out, indent=1, default=str))


# ── phase: the replay on 277 campaigns ────────────────────────────────────────────────

FIRE_COLS = ["ticker", "ep_date", "era", "tier", "rung", "fire_date", "session_idx", "fire_minute", "resolution",
             "entry", "stop", "prior_low", "ep_close", "ep_high", "ep_low", "adr_dollar", "adr_n", "source",
             "day0_resolved", "day0_post_low", "day0_post_high",
             "settle_status", "settle_reason", "outcome", "realized_r", "outcome_trail", "realized_r_trail",
             "mfe_r", "mae_r", "reached_4r"]
COVERAGE_MIN_FRAC = 0.5      # a campaign with fewer than half its forward sessions minute-covered is UNCOVERED


def campaign_coverage(a, raw):
    sess = _trading_days(a["ep_date"] + timedelta(days=1), LAST_SESSION)[:WINDOW]
    have = sum(1 for d in sess if (a["ticker"], d) in raw)
    return have, len(sess)


def lane_recorded_first_fires(keys):
    """The live lane's own recorded FIRST-attempt fires on the given (ticker, ep_date) campaigns, from
    today's Block 5 extract (`_327_block5/trigger.csv`), with the day-0 excursion cache and the
    production settlement columns. Used ONLY for the ERA B campaigns prod holds no minute bars for."""
    out = []
    with open(REPO / "scripts/probes/_327_block5/trigger.csv", newline="") as fh:
        for r in csv.DictReader(fh):
            k = (r["ticker"], date.fromisoformat(r["ep_date"]))
            if k not in keys or r["reentry_shape"] != "first":
                continue
            fm = int(r["fire_minute_et"]) if r.get("fire_minute_et") else None
            out.append({"ticker": r["ticker"], "ep_date": k[1], "rung": r["rung"], "fire_date": date.fromisoformat(r["fire_date"]),
                        "session_idx": int(r["session_idx"]) if r.get("session_idx") else None, "fire_minute": fm,
                        "resolution": r["resolution"], "entry": float(r["entry_price"]), "stop": float(r["stop_price"]),
                        "prior_low": _f(r.get("prior_session_low")), "source": "lane_recorded",
                        "day0_resolved": (r.get("day0_resolved") or "").lower() in ("t", "true", "1"),
                        "day0_post_low": _f(r.get("day0_post_low")), "day0_post_high": _f(r.get("day0_post_high")),
                        "settle_status": "settled" if r.get("outcome") in ("stop", "time_exit") else (r.get("outcome") or "open"),
                        "settle_reason": r.get("stop_hit_date"), "outcome": r.get("outcome"), "realized_r": _f(r.get("realized_r")),
                        "outcome_trail": r.get("outcome_trail"), "realized_r_trail": _f(r.get("realized_r_trail")),
                        "mfe_r": _f(r.get("mfe_r")), "mae_r": _f(r.get("mae_r")), "reached_4r": r.get("reached_4r"),
                        "rec_r_trail_s10": _f(r.get("r_trail_s10")), "rec_r_none_s10": _f(r.get("r_none_s10")),
                        "rec_r_trail_s20": _f(r.get("r_trail_s20")), "rec_r_none_s20": _f(r.get("r_none_s20"))})
    return out


def phase_replay():
    bf.LAST_DATA_DAY = LAST_SESSION
    alerts, daily = load_alerts(), load_daily()
    raw, dropped = load_minutes_raw()
    minutes = minutes_to_5min(raw)
    camps = []
    uncovered = {}
    for a in alerts:
        c = bf.walk_campaign(a, daily, minutes, set())
        c["era"], c["tier"] = a["era"], a["tier"]
        have, n_s = campaign_coverage(a, raw)
        c["cov_have"], c["cov_sessions"] = have, n_s
        bars = daily.get(a["ticker"], {})
        epb = bars.get(a["ep_date"]) or {}
        ordered = sorted(bars)
        adr, adr_n = compute_ep_adr_dollar([bars[d] for d in ordered], a["ep_date"], epb.get("close"))
        for f in c["fires"]:
            f["source"] = "replay"
        c["fires_replay"] = list(c["fires"])
        # ERA B campaigns prod holds (almost) no minute bars for: the replay cannot see their minute-grade
        # fires (17 of the lane's 37 recorded first fires were missing, one fired on a later covered session).
        # Pre-registered handling: the lane's OWN recorded first fires replace the replay on those campaigns.
        if a["era"] == "B" and n_s and have < COVERAGE_MIN_FRAC * n_s:
            uncovered[(a["ticker"], a["ep_date"])] = (have, n_s, len(c["fires"]))
            c["fires"] = lane_recorded_first_fires({(a["ticker"], a["ep_date"])})
        for f in c["fires"]:
            if f.get("prior_low") is None:
                prior = [d for d in ordered if d < f["fire_date"] and bars[d]["low_price"] is not None]
                f["prior_low"] = bars[prior[-1]]["low_price"] if prior else None
            f["ep_close"], f["ep_high"], f["ep_low"] = epb.get("close"), epb.get("high_price"), epb.get("low_price")
            f["adr_dollar"], f["adr_n"] = adr, adr_n
        camps.append(c)
    low_cov_a = [(c["ticker"], str(c["ep_date"]), c["cov_have"], c["cov_sessions"]) for c in camps
                 if c["era"] == "A" and c["cov_sessions"] and c["cov_have"] < COVERAGE_MIN_FRAC * c["cov_sessions"]]
    print(f"UNCOVERED ERA B campaigns (replay fires replaced by the lane's recorded first fires): "
          f"{ {f'{k[0]} {k[1]}': v for k, v in uncovered.items()} }")
    print(f"ERA A campaigns under the same coverage line (kept as replay; nothing to substitute): {len(low_cov_a)} {low_cov_a[:10]}")
    # the lane's recorded settlement on ALL ERA B first fires — the direction cross-check table
    era_b_keys = {(a["ticker"], a["ep_date"]) for a in alerts if a["era"] == "B"}
    rec_all = lane_recorded_first_fires(era_b_keys)
    with open(HERE / "era_b_lane_recorded.tsv", "w") as fh:
        cols = ["ticker", "ep_date", "rung", "fire_date", "fire_minute", "entry", "stop", "outcome", "realized_r", "realized_r_trail",
                "rec_r_none_s10", "rec_r_trail_s10", "rec_r_none_s20", "rec_r_trail_s20", "mfe_r", "settle_reason"]
        fh.write("|".join(cols) + "\n")
        for r in rec_all:
            fh.write("|".join("" if r.get(k) is None else str(r.get(k)) for k in cols) + "\n")
    print(f"ERA B lane-recorded first fires written: {len(rec_all)} rows (era_b_lane_recorded.tsv)")
    with open(HERE / "campaigns.tsv", "w") as fh:
        cols = ["ticker", "ep_date", "era", "tier", "gap_pct", "enroll_status", "sessions_expected", "sessions_walked",
                "sessions_abstained", "complete20", "max_high_pct", "max_adr_mult", "adr_dollar", "cov_have", "cov_sessions"]
        fh.write("|".join(cols) + "\n")
        for c in camps:
            fh.write("|".join("" if c.get(k) is None else str(c.get(k)) for k in cols) + "\n")
    with open(HERE / "fires.tsv", "w") as fh:
        fh.write("|".join(FIRE_COLS) + "\n")
        for c in camps:
            for f in c["fires"]:
                f = {**f, "ticker": c["ticker"], "ep_date": c["ep_date"], "era": c["era"], "tier": c["tier"]}
                fh.write("|".join("" if f.get(k) is None else str(f.get(k)) for k in FIRE_COLS) + "\n")
    # ── COUNTS ONLY (population sizing; no outcome is printed here) ──
    n_f = sum(len(c["fires"]) for c in camps)
    print(f"{len(camps)} campaigns walked ({sum(1 for c in camps if c['enroll_status'] != 'ok')} unenrollable); "
          f"{n_f} first-attempt fires ({sum(1 for c in camps for f in c['fires'] if f['source'] == 'replay')} replayed, "
          f"{sum(1 for c in camps for f in c['fires'] if f['source'] == 'lane_recorded')} lane-recorded on uncovered ERA B campaigns); "
          f"sessions abstained {sum(c['sessions_abstained'] for c in camps)} of "
          f"{sum(c['sessions_walked'] + c['sessions_abstained'] for c in camps)}; "
          f"minute sessions dropped (<{MIN_MINUTE_BARS} bars) {len(dropped)}")
    for era in ("A", "B"):
        cs = [c for c in camps if c["era"] == era]
        fired = {(c["ticker"], c["ep_date"]) for c in cs if c["fires"]}
        print(f"  ERA {era}: {len(cs)} campaigns, family fired on {len(fired)}; fires "
              f"{sum(len(c['fires']) for c in cs)}; abstained sessions {sum(c['sessions_abstained'] for c in cs)}")
        for p in PATTERNS:
            fs = [f for c in cs for f in c["fires"] if f["rung"] == p]
            el10 = sum(1 for f in fs if len(_trading_days(f["fire_date"] + timedelta(days=1), LAST_SESSION)) >= 10)
            el20 = sum(1 for f in fs if len(_trading_days(f["fire_date"] + timedelta(days=1), LAST_SESSION)) >= 20)
            names = len({c["ticker"] for c in cs for f in c["fires"] if f["rung"] == p})
            print(f"    {p:20s} fires {len(fs):4d}  names {names:4d}  elapsed>=10 {el10:4d}  elapsed>=20 {el20:4d}  "
                  f"minute-grade {sum(1 for f in fs if f['fire_minute'] is not None)}  "
                  f"lane-recorded {sum(1 for f in fs if f['source'] == 'lane_recorded')}")
    # ── ANCHOR 3: the live lane's recorded first fires on the ERA B campaigns ──
    era_b = {(c["ticker"], c["ep_date"]) for c in camps if c["era"] == "B"}
    rec = []
    with open(REPO / "scripts/probes/_327_block5/trigger.csv", newline="") as fh:
        for r in csv.DictReader(fh):
            k = (r["ticker"], date.fromisoformat(r["ep_date"]))
            if k in era_b and r["reentry_shape"] == "first":
                rec.append((r["ticker"], r["ep_date"], r["rung"], r["fire_date"], round(float(r["entry_price"]), 4),
                            round(float(r["stop_price"]), 4), r["fire_minute_et"]))
    mine = {}
    for c in camps:
        if c["era"] != "B":
            continue
        for f in c["fires_replay"]:
            mine[(c["ticker"], str(c["ep_date"]), f["rung"])] = (str(f["fire_date"]), round(f["entry"], 4),
                                                                 round(f["stop"], 4), f["fire_minute"])
    exact = same_day = missing = diff = 0
    lines = []
    for r in sorted(rec):
        k = (r[0], r[1], r[2])
        m = mine.get(k)
        if m is None:
            missing += 1; lines.append(f"    MISSING in replay: {r}"); continue
        if m[0] == r[3] and abs(m[1] - r[4]) < 0.006 and abs(m[2] - r[5]) < 0.006:
            exact += 1
        elif m[0] == r[3]:
            same_day += 1; lines.append(f"    same day, prices differ: live {r} replay {m}")
        else:
            diff += 1; lines.append(f"    DIFFERENT day: live {r} replay {m}")
    extra = [k for k in mine if k not in {(r[0], r[1], r[2]) for r in rec}]
    print(f"ANCHOR 3 — live lane's recorded first fires on the 16 ERA B campaigns: {len(rec)} rows; replay matches "
          f"exact {exact}, same day/prices differ {same_day}, different day {diff}, missing {missing}; "
          f"replay fires the lane did not record {len(extra)} {extra[:8]}")
    for ln in lines:
        print(ln)


# ── phase: analyze ────────────────────────────────────────────────────────────────────

def load_fires():
    out = []
    for r in read_tsv(HERE / "fires.tsv"):
        r["ep_date"] = date.fromisoformat(r["ep_date"]); r["fire_date"] = date.fromisoformat(r["fire_date"])
        for k in ("entry", "stop", "prior_low", "ep_close", "ep_high", "ep_low", "adr_dollar", "realized_r",
                  "realized_r_trail", "mfe_r", "mae_r"):
            r[k] = _f(r[k])
        r["fire_minute"] = int(float(r["fire_minute"])) if r["fire_minute"] not in ("", None) else None
        r["session_idx"] = int(float(r["session_idx"])) if r["session_idx"] not in ("", None) else None
        r["day0_resolved"] = (r.get("day0_resolved") or "").lower() in ("true", "t", "1")
        r["day0_post_low"], r["day0_post_high"] = _f(r.get("day0_post_low")), _f(r.get("day0_post_high"))
        r["id"] = f"{r['ticker']}|{r['ep_date']}|{r['rung']}"
        out.append(r)
    return out


_TD = {}


def sessions_after(d):
    if d not in _TD:
        _TD[d] = _trading_days(d + timedelta(days=1), LAST_SESSION)[:WINDOW]
    return _TD[d]


def build_row(t, conv, daily, minutes5, raw1):
    """A P3/P6-shaped row for one replayed fire (both probes' walkers read these keys)."""
    dft = daily.get(t["ticker"], {})
    fb = dft.get(t["fire_date"])
    adr = t["adr_dollar"]
    if adr is None or not t["entry"] or t["entry"] <= 0 or not fb or fb["close"] is None:
        return None, "no_adr_or_entry_or_fire_bar"
    level = t["entry"]
    entry = level
    level_priced = t["fire_minute"] is None
    gap_over_adr = 0.0
    if conv == "fillable" and level_priced and fb["open_price"] and fb["open_price"] > entry:
        gap_over_adr = (fb["open_price"] - entry) / adr
        entry = fb["open_price"]
    sessions = sessions_after(t["fire_date"])
    sess, hole = [], None
    sh, sl, sc, so, sv = [], [], [], [], []
    for j, d in enumerate(sessions, start=1):
        b = dft.get(d)
        if not b or b["high_price"] is None or b["low_price"] is None or b["close"] is None:
            hole = j
            break
        sess.append((b["open_price"], b["high_price"], b["low_price"], b["close"]))
        sh.append(b["high_price"]); sl.append(b["low_price"]); sc.append(b["close"]); so.append(b["open_price"])
        sv.append(b["volume"] if b["volume"] is not None else 0.0)
    pre_dates = [d for d in sorted(dft) if d < t["fire_date"] and dft[d]["close"] is not None]
    closes_pre = [dft[d]["close"] for d in pre_dates]
    vols_pre = [dft[d]["volume"] if dft[d]["volume"] is not None else 0.0 for d in pre_dates]
    prior_cut = t["fire_date"] - timedelta(days=PRIOR_CLOSES_CAL_DAYS)
    allc = closes_pre + [fb["close"]] + sc
    allv = vols_pre + [fb["volume"] if fb["volume"] is not None else 0.0] + sv
    P = len(closes_pre)
    # day 0 — the same source order as Block 5 P3: real post-fire 5-min bars, else (lane-recorded rows only)
    # the row's cached day-0 excursion via the production `day0_pseudo_bars`, else no source
    if level_priced:
        d0_kind, d0_bars = "daily_fold", [(fb["high_price"], fb["low_price"])]
    else:
        bars5 = minutes5.get((t["ticker"], t["fire_date"])) or []
        post5 = [b for b in bars5 if b["m"] > t["fire_minute"]]
        if bars5:
            d0_kind, d0_bars = "real_intraday_bars", [(b["h"], b["l"]) for b in post5]
        else:
            pb = p3_grid.day0_pseudo_bars(t.get("day0_resolved"), t.get("day0_post_low"), t.get("day0_post_high")) \
                if t.get("source") == "lane_recorded" else None
            d0_kind, d0_bars = ("cached_pseudo_bars", [(b["h"], b["l"]) for b in pb]) if pb is not None else ("no_source", None)
    mins = [{"m": b["m"], "o": b["o"], "h": b["h"], "l": b["l"], "c": b["c"]}
            for b in (raw1.get((t["ticker"], t["fire_date"])) or [])]
    row = {"id": t["id"], "ticker": t["ticker"], "ep_date": t["ep_date"], "rung": t["rung"], "era": t["era"],
           "tier": t["tier"], "fire_date": t["fire_date"], "session_idx": t["session_idx"], "source": t.get("source"),
           "resolution": t["resolution"], "elapsed": len(sessions), "hole": hole, "n_avail": len(sc),
           "f": 1.0, "entry": entry, "level": level, "adr": adr, "level_priced": level_priced,
           "gap_over_adr": gap_over_adr, "d0_kind": d0_kind, "sessions": sessions, "sess": sess,
           "c": [fb["close"]] + sc, "o": [None] + so, "_sh": sh, "_sl": sl, "allc": allc, "allv": allv, "P": P,
           "prior_40": [dft[d]["close"] for d in pre_dates if d >= prior_cut], "mins": mins,
           "fire_minute": t["fire_minute"], "day_low": fb["low_price"], "day_high": fb["high_price"],
           "day_close": fb["close"], "day_open": fb["open_price"],
           "exit_era": exit_era_label(t["fire_date"], "magna53"),
           "rules": exit_rules_as_of(t["fire_date"], "magna53"),
           "rules_today": exit_rules_as_of(TODAY_RULES_DATE, "magna53"),
           "half": {K: t["era"] for K in CHECKPOINTS},          # P6's aggregate reads this key; era here
           "stops": {}}
    for s in STOPS:
        if s == "incumbent":
            lvl = t["stop"]
        elif s == "prior_low":
            lvl = t["prior_low"]
        else:
            lvl = entry - ADR_MULT[s] * adr
        if lvl is None or lvl >= entry or lvl <= 0:
            row["stops"][s] = {"level": lvl, "killed": True,
                               "why": "stop_le_0" if (lvl is not None and lvl <= 0) else "stop_ge_entry"}
            continue
        if d0_kind == "no_source":
            d0_abstain = row["day_low"] is not None and row["day_low"] <= lvl
            d0 = [] if not d0_abstain else None
        else:
            d0_abstain, d0 = False, d0_bars
        row["stops"][s] = {"level": lvl, "killed": False, "risk": entry - lvl,
                           "width_pct": (entry - lvl) / entry * 100.0, "d0_abstain": d0_abstain, "d0_bars": d0}
    return row, None


def gap_charged(row, st, kind, ev_s, R):
    """House R → gap-charged R: a stop at session s >= 1 whose session OPENED below the stop fills at the open."""
    if kind == STOP and ev_s is not None and ev_s >= 1:
        o = row["o"][ev_s]
        if o is not None and o < st["level"]:
            return (o - row["entry"]) / st["risk"]
    return R


def _mean(v):
    return round(float(np.mean(v)), 4) if len(v) else None


def _pct(a, b):
    return round(100.0 * a / b, 2) if b else None


def aggregate(scored, incumbent_tail_pct=None):
    """scored: dicts {row, R, R_gap, kind, era, width_ok}. Legs on ERA A; ERA B direction; pooled n."""
    fl = [x for x in scored if x["width_ok"]]

    def block(xs):
        R = [x["R"] for x in xs]
        Rg = [x["R_gap"] for x in xs]
        n = len(R)
        losses = [r for r in Rg if r < 0]
        tail = sum(1 for r in R if r >= TAIL_R - _EPS)
        by_name = defaultdict(float)
        for x in xs:
            by_name[x["row"]["ticker"]] += x["R"]
        drop = None
        if by_name:
            best = max(by_name, key=by_name.get)
            v = [x["R"] for x in xs if x["row"]["ticker"] != best]
            drop = {"name": best, "name_sum_r": round(by_name[best], 2), "n": len(v), "mean_r": _mean(v)}
        return {"n": n, "n_names": len({x["row"]["ticker"] for x in xs}), "mean_r": _mean(R),
                "median_r": round(float(np.median(R)), 4) if n else None, "sum_r": round(float(np.sum(R)), 2) if n else None,
                "gap_mean_r": _mean(Rg), "tail3": tail, "tail3_pct": _pct(tail, n),
                "win_pct": _pct(sum(1 for r in R if r > 0), n), "avg_loss_gap": _mean(losses), "loss_pct": _pct(len(losses), n),
                "stop_pct": _pct(sum(1 for x in xs if x["kind"] == STOP), n),
                "exit_pct": _pct(sum(1 for x in xs if x["kind"] in (EXIT, "trail")), n),
                "target_pct": _pct(sum(1 for x in xs if x["kind"] == TARGET), n),
                "open_pct": _pct(sum(1 for x in xs if x["kind"] == OPEN), n),
                "best_r": round(max(R), 3) if n else None, "worst_r": round(min(Rg), 3) if n else None,
                "drop_best": drop,
                "per_pattern": {p: {"n": len([x for x in xs if x["row"]["rung"] == p]),
                                    "mean_r": _mean([x["R"] for x in xs if x["row"]["rung"] == p]),
                                    "tail3": sum(1 for x in xs if x["row"]["rung"] == p and x["R"] >= TAIL_R - _EPS)}
                                for p in PATTERNS}}
    out = {"n_unfloored": len(scored), "pooled": block(fl),
           "era_a": block([x for x in fl if x["era"] == "A"]), "era_b": block([x for x in fl if x["era"] == "B"])}
    A, B, Pp = out["era_a"], out["era_b"], out["pooled"]
    tail_bar = None if incumbent_tail_pct is None else PASS["tail_mult"] * incumbent_tail_pct
    L = {"mean_r_gt_0_A": A["mean_r"] is not None and A["mean_r"] > 0,
         "tail_ge_3x_incumbent_A": (tail_bar is not None and A["tail3_pct"] is not None and A["tail3_pct"] >= tail_bar - _EPS),
         "tail_ge_3pct_abs_A": A["tail3_pct"] is not None and A["tail3_pct"] >= PASS["tail_abs_pct"] - _EPS,
         "avg_loss_ge_m1_A": A["avg_loss_gap"] is None or A["avg_loss_gap"] >= PASS["avg_loss"] - _EPS,
         "drop_best_name_A": A["drop_best"] is not None and A["drop_best"]["mean_r"] is not None and A["drop_best"]["mean_r"] > 0,
         "era_b_same_sign": (B["n"] > 0 and A["mean_r"] is not None and B["mean_r"] is not None
                             and ((A["mean_r"] > 0) == (B["mean_r"] > 0))),
         "pooled_n_ge_150_names_ge_60": Pp["n"] >= PASS["n"] and Pp["n_names"] >= PASS["names"]}
    L["clears_era_a"] = all(L[k] for k in ("mean_r_gt_0_A", "tail_ge_3x_incumbent_A", "avg_loss_ge_m1_A",
                                          "drop_best_name_A", "pooled_n_ge_150_names_ge_60"))
    L["clears"] = L["clears_era_a"] and L["era_b_same_sign"]
    L["clears_with_abs_tail"] = all(L[k] for k in ("mean_r_gt_0_A", "tail_ge_3pct_abs_A", "avg_loss_ge_m1_A",
                                                  "drop_best_name_A", "pooled_n_ge_150_names_ge_60")) and L["era_b_same_sign"]
    out["legs"] = L
    out["tail_bar_pct"] = tail_bar
    return out


def run_m1_arm(row, st, conv, arm, K, sw):
    """P6's run_m1, with the 'today' variants swapping in today's rules."""
    if arm.startswith("M1t_"):
        row2 = dict(row); row2["rules"] = row["rules_today"]
        return p6.run_m1(row2, st, conv, "M1_" + arm.split("_", 1)[1], K, sw)
    return p6.run_m1(row, st, conv, arm, K, sw)


def phase_analyze():
    fires = load_fires()
    alerts = load_alerts()
    daily = load_daily()
    raw1, dropped = load_minutes_raw()
    minutes5 = minutes_to_5min(raw1)
    summary = {"draws": {"grid": N_GRID, "mgmt": N_MGMT, "total": N_DRAWS, "noise_band_max": 7, "family_min": 55},
               "population": {"campaigns": len(alerts), "fires": len(fires),
                              "era": {e: {"campaigns": sum(1 for a in alerts if a["era"] == e),
                                          "fires": sum(1 for f in fires if f["era"] == e)} for e in ("A", "B")}}}
    print(f"fires {len(fires)} on {len({f['ticker'] for f in fires})} names; draws {N_DRAWS} = {N_GRID} grid + {N_MGMT} mgmt")

    rows = {c: [] for c in CONVENTIONS}
    excl = Counter()
    for conv in CONVENTIONS:
        for t in fires:
            row, why = build_row(t, conv, daily, minutes5, raw1)
            if row is None:
                excl[(conv, why)] += 1
                continue
            row["fp"] = p3_grid.first_passages(row)
            row["ex"] = p3_grid.exit_sessions(row)
            rows[conv].append(row)
    print(f"rows built {len(rows['recorded'])} / {len(rows['fillable'])}; excluded {dict(excl)}; "
          f"d0 kinds {dict(Counter(r['d0_kind'] for r in rows['recorded']))}; "
          f"level-priced fires opening above the level {sum(1 for r in rows['fillable'] if r['gap_over_adr'] > 0)}")
    summary["rows"] = {"recorded": len(rows["recorded"]), "excluded": {f"{k[0]}:{k[1]}": v for k, v in excl.items()},
                       "d0_kinds": dict(Counter(r["d0_kind"] for r in rows["recorded"])),
                       "elapsed_ge10": {e: sum(1 for r in rows["recorded"] if r["elapsed"] >= 10 and r["era"] == e) for e in "AB"},
                       "elapsed_ge20": {e: sum(1 for r in rows["recorded"] if r["elapsed"] >= 20 and r["era"] == e) for e in "AB"}}

    # ── ANCHOR 4: the incumbent grid cell == the REAL compute_settlement on the same inputs ──
    va = Counter()
    for row in rows["recorded"]:
        st = row["stops"]["incumbent"]
        if st["killed"] or st["d0_abstain"]:
            va["killed_or_abstain"] += 1
            continue
        t = next(f for f in fires if f["id"] == row["id"])
        bars = daily[row["ticker"]]
        fdb = {"h": row["day_high"], "l": row["day_low"], "c": row["day_close"]}
        bars5 = minutes5.get((row["ticker"], row["fire_date"]))
        post5 = None
        if row["fire_minute"] is not None and bars5:
            post5 = [b for b in bars5 if b["m"] > row["fire_minute"]]
        res = compute_settlement(entry=row["entry"], stop=st["level"], fire_minute=row["fire_minute"], fire_day_bar=fdb,
                                 post_fire_bars5=post5, sessions=_trading_days(row["fire_date"] + timedelta(days=1), LAST_SESSION),
                                 bars_by_day=bars, closes_before_fire=row["allc"][:row["P"]])
        fp = row["fp"][("incumbent", "none")]
        for K in CHECKPOINTS:
            if row["elapsed"] < K:
                continue
            for ex, col in (("none", f"r_none_s{K}"), ("trail_max10_20", f"r_trail_s{K}")):
                stt, R, kind, ev = p3_grid.cell_r(row, st, fp, row["ex"][ex], K)
                if res["status"] != "settled":
                    va[f"settle_{res['status']}"] += 1
                    continue
                ref = res.get(col)
                if stt != "scored" or ref is None:
                    va["not_comparable"] += 1
                    continue
                ok = abs(R - ref) <= 0.002
                va[f"s{K}_{ex}_" + ("match" if ok else "mismatch")] += 1
                if not ok and va["printed"] < 8:
                    va["printed"] += 1
                    print(f"  ANCHOR 4 mismatch {row['ticker']} {row['fire_date']} {row['rung']} s{K} {ex}: grid {R:.4f} vs compute_settlement {ref}")
    va.pop("printed", None)
    summary["anchor4_grid_vs_compute_settlement"] = dict(va)
    print("ANCHOR 4 — grid incumbent cell vs REAL compute_settlement:", dict(va))

    # ── the incumbent rate (stated before any cell) ──
    def scored_grid(conv, K, s, tg, ex):
        out = []
        for row in rows[conv]:
            st = row["stops"][s]
            if st["killed"] or st["d0_abstain"] or row["elapsed"] < K:
                continue
            fp = row["fp"].get((s, tg))
            if fp is None:
                continue
            stt, R, kind, ev = p3_grid.cell_r(row, st, fp, row["ex"][ex], K)
            if stt != "scored":
                continue
            out.append({"row": row, "R": R, "R_gap": gap_charged(row, st, kind, ev, R), "kind": kind, "era": row["era"],
                        "width_ok": st["width_pct"] >= WIDTH_FLOOR_PCT, "ev_s": ev, "straddle": fp["straddle"],
                        "tail_eligible": fp["tail_eligible"]})
        return out

    inc = {}
    for K in CHECKPOINTS:
        a = aggregate(scored_grid("recorded", K, "incumbent", "none", "trail_max10_20"))
        inc[K] = a
        an = aggregate(scored_grid("recorded", K, "incumbent", "none", "none"))
        print(f"INCUMBENT (incumbent stop / no target / trail max10_20) s{K}: ERA A n={a['era_a']['n']} mean {a['era_a']['mean_r']} "
              f"kept>=3R {a['era_a']['tail3']} ({a['era_a']['tail3_pct']}%) stopped {a['era_a']['stop_pct']}% | ERA B n={a['era_b']['n']} "
              f"mean {a['era_b']['mean_r']} kept>=3R {a['era_b']['tail3_pct']}% | pooled n={a['pooled']['n']} mean {a['pooled']['mean_r']} "
              f"kept>=3R {a['pooled']['tail3_pct']}%;  no-exit arm ERA A mean {an['era_a']['mean_r']} kept>=3R {an['era_a']['tail3_pct']}%")
    incumbent_tail_A = inc[PRIMARY_K]["era_a"]["tail3_pct"] or 0.0
    tail_bar = PASS["tail_mult"] * incumbent_tail_A
    summary["incumbent"] = {f"s{K}": inc[K] for K in CHECKPOINTS}
    summary["tail_bar_pct_3x_incumbent_A_s10"] = tail_bar
    print(f"TAIL BAR = 3 x {incumbent_tail_A}% = {tail_bar:.2f}% (3.0% absolute reported beside)")

    # ── B: every cell ──
    cells = {}
    events = []
    for conv in CONVENTIONS:
        for K in CHECKPOINTS:
            for s in STOPS:
                for tg in TARGETS:
                    for ex in EXITS:
                        sc = scored_grid(conv, K, s, tg, ex)
                        a = aggregate(sc, incumbent_tail_A)
                        a["straddle_decided"] = sum(1 for x in sc if x["straddle"] and x["width_ok"])
                        a["tail_eligible"] = all(x["tail_eligible"] for x in sc) if sc else None
                        cells[(conv, K, "grid", s, tg, ex)] = a
                        if K == PRIMARY_K and conv == "recorded":
                            for x in sc:
                                events.append({"kind": "grid", "id": x["row"]["id"], "era": x["era"], "stop": s, "target": tg,
                                               "exit": ex, "R": round(x["R"], 4), "R_gap": round(x["R_gap"], 4),
                                               "ev": x["kind"], "ev_s": x["ev_s"], "width_ok": x["width_ok"]})
        # management arms
        per_row = {}
        for row in rows[conv]:
            sw = p6.walk_arm_sessions(row)
            for s in MGMT_STOPS:
                st = row["stops"][s]
                if st["killed"] or st["d0_abstain"]:
                    continue
                for arm in MGMT_ARMS:
                    rec = {"R": {}, "kind": {}, "partial": False, "be": False}
                    if arm in M1_ARMS:
                        for K in CHECKPOINTS:
                            if row["elapsed"] < K:
                                continue
                            stt, r, meta = run_m1_arm(row, st, conv, arm, K, sw)
                            if stt == "scored":
                                rec["R"][K], rec["kind"][K] = r, meta["final"] or "open"
                                rec["partial"] = rec["partial"] or meta["partial"]
                                rec["src"] = meta["src"]
                            else:
                                rec.setdefault("abstain", {})[K] = f"{stt}:{meta.get('reason')}"
                        stt, r, meta = run_m1_arm(row, st, conv, arm, WINDOW, sw)
                        if stt in ("scored", "marked_last"):
                            rec["R_final"], rec["final_kind"] = r, meta["final"]
                    else:
                        p_r, be_r, remn = p6.grid_params(arm)
                        ex_, remn_, cs, pt, be = p6.walk_mgmt(row["entry"], st["level"], st["d0_bars"], row["sess"], row["allc"],
                                                              row["P"], p_r, be_r, remn)
                        rec["partial"], rec["be"] = pt, be
                        for K in CHECKPOINTS:
                            if row["elapsed"] < K:
                                continue
                            r, k = p6.r_at(ex_, cs, row["entry"], st["risk"], row["allc"], row["P"], row["n_avail"], K, gap=True)
                            if r is not None:
                                rec["R"][K], rec["kind"][K] = r, k
                        Kf = min(WINDOW, row["n_avail"])
                        r, k = p6.r_at(ex_, cs, row["entry"], st["risk"], row["allc"], row["P"], row["n_avail"], Kf, gap=True)
                        if r is not None:
                            rec["R_final"], rec["final_kind"] = r, k
                    per_row[(row["id"], s, arm)] = rec
        for K in CHECKPOINTS:
            for s in MGMT_STOPS:
                for arm in MGMT_ARMS:
                    sc = []
                    for row in rows[conv]:
                        if row["elapsed"] < K:
                            continue
                        rec = per_row.get((row["id"], s, arm))
                        if rec is None or K not in rec["R"]:
                            continue
                        st = row["stops"][s]
                        sc.append({"row": row, "R": rec["R"][K], "R_gap": rec["R"][K], "kind": rec["kind"][K], "era": row["era"],
                                   "width_ok": st["width_pct"] >= WIDTH_FLOOR_PCT, "partial": rec["partial"], "be": rec["be"]})
                    a = aggregate(sc, incumbent_tail_A)
                    a["partial_pct"] = _pct(sum(1 for x in sc if x["partial"] and x["width_ok"]), a["pooled"]["n"])
                    a["be_pct"] = _pct(sum(1 for x in sc if x["be"] and x["width_ok"]), a["pooled"]["n"])
                    if arm in M1_ARMS:
                        a["exit_era_n"] = dict(Counter(x["row"]["exit_era"] for x in sc if x["width_ok"]))
                        a["abstained"] = sum(1 for row in rows[conv] if row["elapsed"] >= K and (row["id"], s, arm) in per_row
                                             and K in per_row[(row["id"], s, arm)].get("abstain", {}))
                    cells[(conv, K, "mgmt", s, arm, "")] = a
        rows[conv + "_per_row"] = per_row

    # cells table + clearing counts
    with open(HERE / "cells.tsv", "w") as fh:
        cols = ["convention", "K", "kind", "stop", "target_or_arm", "exit", "n_A", "names_A", "mean_A", "median_A", "tail3_A",
                "tail3_pct_A", "avg_loss_gap_A", "stop_pct_A", "drop_best_A", "drop_best_mean_A", "n_B", "mean_B", "tail3_pct_B",
                "n_pooled", "names_pooled", "mean_pooled", "tail3_pct_pooled", "clears_era_a", "era_b_same_sign", "clears",
                "clears_with_abs_tail", "legs_failed"]
        fh.write("\t".join(cols) + "\n")
        for k, a in cells.items():
            conv, K, kind, s, tg, ex = k
            A, B, Pp, L = a["era_a"], a["era_b"], a["pooled"], a["legs"]
            failed = ",".join(n for n in ("mean_r_gt_0_A", "tail_ge_3x_incumbent_A", "avg_loss_ge_m1_A", "drop_best_name_A",
                                          "era_b_same_sign", "pooled_n_ge_150_names_ge_60") if not L[n])
            fh.write("\t".join(str(v) for v in (conv, K, kind, s, tg, ex, A["n"], A["n_names"], A["mean_r"], A["median_r"], A["tail3"],
                                                A["tail3_pct"], A["avg_loss_gap"], A["stop_pct"],
                                                A["drop_best"]["name"] if A["drop_best"] else None,
                                                A["drop_best"]["mean_r"] if A["drop_best"] else None, B["n"], B["mean_r"], B["tail3_pct"],
                                                Pp["n"], Pp["n_names"], Pp["mean_r"], Pp["tail3_pct"], L["clears_era_a"], L["era_b_same_sign"],
                                                L["clears"], L["clears_with_abs_tail"], failed)) + "\n")
    verdict = {}
    for conv in CONVENTIONS:
        for K in CHECKPOINTS:
            ks = [k for k in cells if k[0] == conv and k[1] == K]
            cl = [k for k in ks if cells[k]["legs"]["clears"]]
            clA = [k for k in ks if cells[k]["legs"]["clears_era_a"]]
            posA = [k for k in ks if cells[k]["era_a"]["mean_r"] is not None and cells[k]["era_a"]["mean_r"] > 0]
            posB = [k for k in ks if cells[k]["era_b"]["mean_r"] is not None and cells[k]["era_b"]["mean_r"] > 0]
            posP = [k for k in ks if cells[k]["pooled"]["mean_r"] is not None and cells[k]["pooled"]["mean_r"] > 0]
            tailA = [k for k in ks if cells[k]["legs"]["tail_ge_3x_incumbent_A"]]
            bestA = max(ks, key=lambda k: (cells[k]["era_a"]["mean_r"] if cells[k]["era_a"]["mean_r"] is not None else -9))
            verdict[f"{conv}_s{K}"] = {
                "draws": len(ks), "clearing": len(cl), "clearing_era_a_only": len(clA),
                "clearing_with_abs_tail": sum(1 for k in ks if cells[k]["legs"]["clears_with_abs_tail"]),
                "cells_mean_gt0_era_a": len(posA), "cells_mean_gt0_era_b": len(posB), "cells_mean_gt0_pooled": len(posP),
                "cells_tail_ge_bar_era_a": len(tailA),
                "cells_mean_gt0_era_a_AND_era_b": len(set(posA) & set(posB)),
                "best_era_a_cell": {"cell": bestA[2:], "era_a": {k2: cells[bestA]["era_a"][k2] for k2 in ("n", "mean_r", "tail3_pct", "avg_loss_gap")},
                                    "era_b": {k2: cells[bestA]["era_b"][k2] for k2 in ("n", "mean_r")}, "legs": cells[bestA]["legs"]},
                "clearing_cells": [{"cell": k[2:], "era_a": cells[k]["era_a"], "era_b": {k2: cells[k]["era_b"][k2] for k2 in ("n", "mean_r", "tail3_pct")},
                                    "pooled": {k2: cells[k]["pooled"][k2] for k2 in ("n", "n_names", "mean_r", "tail3_pct")}} for k in cl][:40],
                "clearing_era_a_cells": [{"cell": k[2:], "era_a_mean": cells[k]["era_a"]["mean_r"], "era_a_n": cells[k]["era_a"]["n"],
                                          "era_b_mean": cells[k]["era_b"]["mean_r"], "era_b_n": cells[k]["era_b"]["n"]} for k in clA][:60]}
            print(f"[{conv} s{K}] draws {len(ks)}: clearing {len(cl)} (ERA A only {len(clA)}; with 3% abs tail {verdict[f'{conv}_s{K}']['clearing_with_abs_tail']}); "
                  f"mean>0 ERA A {len(posA)} / ERA B {len(posB)} / both {len(set(posA) & set(posB))} / pooled {len(posP)}; tail>=bar ERA A {len(tailA)}; "
                  f"best ERA A cell {bestA[2:]} mean {cells[bestA]['era_a']['mean_r']} n {cells[bestA]['era_a']['n']} (ERA B {cells[bestA]['era_b']['mean_r']} n {cells[bestA]['era_b']['n']})")
    summary["verdict"] = verdict
    # per-pattern tail-first read on the recorded s10 grid
    pat_read = {}
    for p in PATTERNS:
        ks = [k for k in cells if k[0] == "recorded" and k[1] == PRIMARY_K]
        best = max(ks, key=lambda k: (cells[k]["era_a"]["per_pattern"][p]["mean_r"] if cells[k]["era_a"]["per_pattern"][p]["mean_r"] is not None
                                       and cells[k]["era_a"]["per_pattern"][p]["n"] >= 30 else -9))
        pp = cells[best]["era_a"]["per_pattern"][p]
        inc_pp = inc[PRIMARY_K]["era_a"]["per_pattern"][p]
        pat_read[p] = {"incumbent_era_a": inc_pp, "best_cell_era_a": {"cell": best[2:], **pp},
                       "cells_mean_gt0_era_a_n_ge_30": sum(1 for k in ks if cells[k]["era_a"]["per_pattern"][p]["mean_r"] is not None
                                                           and cells[k]["era_a"]["per_pattern"][p]["mean_r"] > 0 and cells[k]["era_a"]["per_pattern"][p]["n"] >= 30)}
    summary["per_pattern_tail_first"] = pat_read
    # the exits' effect at stop=adr_100 / no target (recorded s10) and the mgmt family summary
    summary["exits_at_adr100_none_s10"] = {ex: {"era_a": {k2: cells[("recorded", 10, "grid", "adr_100", "none", ex)]["era_a"][k2] for k2 in ("n", "mean_r", "tail3_pct", "exit_pct", "stop_pct", "avg_loss_gap")},
                                                "era_b": {k2: cells[("recorded", 10, "grid", "adr_100", "none", ex)]["era_b"][k2] for k2 in ("n", "mean_r")}} for ex in EXITS}
    summary["mgmt_cells_s10"] = {f"{s}/{arm}": {"era_a": {k2: cells[("recorded", 10, "mgmt", s, arm, "")]["era_a"][k2] for k2 in ("n", "mean_r", "tail3_pct", "avg_loss_gap", "stop_pct")},
                                               "era_b": {k2: cells[("recorded", 10, "mgmt", s, arm, "")]["era_b"][k2] for k2 in ("n", "mean_r")},
                                               "exit_era_n": cells[("recorded", 10, "mgmt", s, arm, "")].get("exit_era_n"),
                                               "partial_pct": cells[("recorded", 10, "mgmt", s, arm, "")].get("partial_pct")}
                                 for s in MGMT_STOPS for arm in MGMT_ARMS}
    summary["mgmt_cells_s20"] = {f"{s}/{arm}": {"era_a": {k2: cells[("recorded", 20, "mgmt", s, arm, "")]["era_a"][k2] for k2 in ("n", "mean_r", "tail3_pct", "avg_loss_gap")}}
                                 for s in MGMT_STOPS for arm in MGMT_ARMS}

    # ── A: entry edge vs the matched control ──
    A_out = {}
    fires_by_campaign = defaultdict(lambda: defaultdict(set))
    for t in fires:
        fires_by_campaign[(t["ticker"], t["ep_date"])][t["rung"]].add(t["fire_date"])
    era_of = {(a["ticker"], a["ep_date"]): a["era"] for a in alerts}

    def walk_fire(row, entry, d0, K, bound):
        stop, tgt = entry - row["adr"], entry + 2.0 * row["adr"]
        bars = d0 + [(h, l) for h, l in zip(row["_sh"], row["_sl"])] + ([None] if row["hole"] is not None else [])
        ev, idx = p2_probe.first_passage(bars, entry, stop, tgt, bound)
        return p2_probe.at_checkpoint(ev, idx, K, len(d0))

    ctl_walks = {}     # (ticker, ep, session_date) -> {bound: outcome at K}
    for (tkr, ep), rungs in fires_by_campaign.items():
        dft = daily.get(tkr, {})
        adr = next(f["adr_dollar"] for f in fires if f["ticker"] == tkr and f["ep_date"] == ep)
        if adr is None:
            continue
        all_fire_dates = set().union(*rungs.values())
        for sdate in sessions_after(ep):
            b = dft.get(sdate)
            if not b or b["close"] is None:
                continue
            after = sessions_after(sdate)
            sbars = [((dft[d]["high_price"], dft[d]["low_price"]) if d in dft and dft[d]["high_price"] is not None else None) for d in after]
            e = b["close"]
            rec = {"elapsed": len(after), "is_fire": sdate in all_fire_dates, "rungs_fired": {p for p in rungs if sdate in rungs[p]}}
            for bnd in ("pess", "opt"):
                for K in (5, 10, 20):
                    if len(after) >= K:
                        ev, idx = p2_probe.first_passage(sbars, e, e - adr, e + 2 * adr, bnd)
                        rec[(bnd, K)] = p2_probe.at_checkpoint(ev, idx, K, 0)
            ctl_walks[(tkr, ep, sdate)] = rec

    def rate(outs):
        n = sum(1 for o in outs if o != ABSTAIN)
        h = sum(1 for o in outs if o == TARGET)
        return n, h, _pct(h, n)

    for p in PATTERNS:
        A_out[p] = {}
        for era in ("A", "B", "all"):
            prow = [r for r in rows["recorded"] if r["rung"] == p and r["elapsed"] >= PRIMARY_K and (era == "all" or r["era"] == era)]
            camps_p = {(r["ticker"], r["ep_date"]) for r in prow}
            res = {"n_fires": len(prow), "names": len({r["ticker"] for r in prow})}
            for bnd in ("pess", "opt"):
                fo, fo_close, fo_fill, co = [], [], [], []
                by_name_f, by_name_c = defaultdict(lambda: [0, 0]), defaultdict(lambda: [0, 0])
                for r in prow:
                    st = r["stops"]["adr_100"]
                    d0 = st["d0_bars"] if (not st["killed"] and not st["d0_abstain"]) else None
                    o = walk_fire(r, r["entry"], d0, PRIMARY_K, bnd) if d0 is not None else ABSTAIN
                    fo.append(o)
                    if o != ABSTAIN:
                        by_name_f[r["ticker"]][0] += 1; by_name_f[r["ticker"]][1] += (o == TARGET)
                    fo_close.append(walk_fire(r, r["day_close"], [], PRIMARY_K, bnd))
                    rf = next((x for x in rows["fillable"] if x["id"] == r["id"]), None)
                    if rf is not None:
                        stf = rf["stops"]["adr_100"]
                        d0f = stf["d0_bars"] if (not stf["killed"] and not stf["d0_abstain"]) else None
                        fo_fill.append(walk_fire(rf, rf["entry"], d0f, PRIMARY_K, bnd) if d0f is not None else ABSTAIN)
                for (tkr, ep, sdate), rec in ctl_walks.items():
                    if (tkr, ep) in camps_p and not rec["is_fire"] and rec["elapsed"] >= PRIMARY_K and (bnd, PRIMARY_K) in rec:
                        o = rec[(bnd, PRIMARY_K)]
                        co.append(o)
                        if o != ABSTAIN:
                            by_name_c[tkr][0] += 1; by_name_c[tkr][1] += (o == TARGET)
                nf, hf, rf_ = rate(fo); nc, hc, rc = rate(co)
                nfc, hfc, rfc = rate(fo_close); nff, hff, rff = rate(fo_fill)
                gap = None if (rf_ is None or rc is None) else round(rf_ - rc, 2)
                # drop the best-contributing name from both sides
                drop = None
                if by_name_f:
                    best = max(by_name_f, key=lambda k: by_name_f[k][1])
                    n2 = nf - by_name_f[best][0]; h2 = hf - by_name_f[best][1]
                    nc2 = nc - by_name_c.get(best, [0, 0])[0]; hc2 = hc - by_name_c.get(best, [0, 0])[1]
                    drop = {"name": best, "gap_pp": None if not (n2 and nc2) else round(100 * h2 / n2 - 100 * hc2 / nc2, 2)}
                res[bnd] = {"fire_n": nf, "fire_pct": rf_, "fire_abstain": sum(1 for o in fo if o == ABSTAIN), "ctl_n": nc, "ctl_pct": rc,
                            "gap_pp": gap, "close_entry_fire_pct": rfc, "close_entry_gap_pp": None if (rfc is None or rc is None) else round(rfc - rc, 2),
                            "fillable_fire_pct": rff, "fillable_gap_pp": None if (rff is None or rc is None) else round(rff - rc, 2),
                            "drop_best_name": drop}
            A_out[p][era] = res
        a, b, al = A_out[p]["A"], A_out[p]["B"], A_out[p]["all"]
        print(f"A {p:20s} ERA A n={a['n_fires']}/{a.get('pess', {}).get('ctl_n')} pess {a.get('pess', {}).get('fire_pct')} vs {a.get('pess', {}).get('ctl_pct')} → {a.get('pess', {}).get('gap_pp')}pp "
              f"(close-entry {a.get('pess', {}).get('close_entry_gap_pp')}pp; fillable {a.get('pess', {}).get('fillable_gap_pp')}pp; drop {a.get('pess', {}).get('drop_best_name')}) | "
              f"ERA B n={b['n_fires']} pess {b.get('pess', {}).get('fire_pct')} vs {b.get('pess', {}).get('ctl_pct')} → {b.get('pess', {}).get('gap_pp')}pp | opt all {al.get('opt', {}).get('gap_pp')}pp")
    summary["A_entry_edge"] = A_out

    # ── D: big winners ──
    runners, rstats = {}, Counter()
    for a in alerts:
        if a["ep_date"] > RUNNER["ep_max"]:
            rstats["unclassifiable_ep_after_09_04"] += 1
            continue
        dft = daily.get(a["ticker"], {})
        eb = dft.get(a["ep_date"])
        if not eb or not eb["close"]:
            rstats["no_ep_bar"] += 1
            continue
        after = _trading_days(a["ep_date"] + timedelta(days=1), LAST_SESSION)[:RUNNER["sessions"]]
        bars = [dft.get(d) for d in after]
        if len(after) < RUNNER["sessions"] or any(b is None or b["high_price"] is None or b["close"] is None for b in bars):
            rstats["incomplete_15_sessions"] += 1
            continue
        rstats["classifiable"] += 1
        base = eb["close"]
        mx = max(b["high_price"] for b in bars) / base
        c15 = bars[-1]["close"] / base
        if mx >= RUNNER["gain"]:
            rstats["ran_50"] += 1
            if c15 >= RUNNER["hold"]:
                rstats["ran_50_held_30"] += 1
                runners[(a["ticker"], a["ep_date"])] = {"era": a["era"], "tier": a["tier"], "base": base, "max_up_pct": round(100 * (mx - 1), 1),
                                                       "s15_pct": round(100 * (c15 - 1), 1),
                                                       "fires": [(f["rung"], f["session_idx"], f["resolution"]) for f in fires if f["ticker"] == a["ticker"] and f["ep_date"] == a["ep_date"]]}
    rstats["runner_campaigns_lane_fired"] = sum(1 for r in runners.values() if r["fires"])
    print(f"D runners: {dict(rstats)}")
    for k, v in sorted(runners.items(), key=lambda kv: -kv[1]["max_up_pct"]):
        print(f"   {k[0]:6s} {k[1]} era {v['era']} {v['tier']:8s} +{v['max_up_pct']}% max, s15 +{v['s15_pct']}%, fires {v['fires']}")
    runner_ids = {f"{k[0]}|{k[1]}|{p}" for k in runners for p in PATTERNS}
    d_arms = {}
    per_row = rows["recorded_per_row"]
    inc_final = {}
    for row in rows["recorded"]:
        st = row["stops"]["incumbent"]
        if st["killed"] or st["d0_abstain"]:
            continue
        Kf = min(WINDOW, row["n_avail"])
        fp = row["fp"][("incumbent", "none")]
        stt, R, kind, ev = p3_grid.cell_r(row, st, fp, row["ex"]["trail_max10_20"], Kf) if Kf > 0 else ("x", None, None, None)
        if stt == "scored":
            inc_final[row["id"]] = R
    run_inc = [inc_final[i] for i in inc_final if i in runner_ids]
    rest_inc = [inc_final[i] for i in inc_final if i not in runner_ids]
    d_arms["incumbent_trail"] = {"runner_fires": len(run_inc), "runner_kept3": sum(1 for r in run_inc if r >= TAIL_R - _EPS),
                                 "runner_mean": _mean(run_inc), "rest_n": len(rest_inc), "rest_mean": _mean(rest_inc)}
    for s in MGMT_STOPS:
        for arm in MGMT_ARMS:
            run_r, rest_r = [], []
            for row in rows["recorded"]:
                rec = per_row.get((row["id"], s, arm))
                if rec is None or rec.get("R_final") is None:
                    continue
                (run_r if row["id"] in runner_ids else rest_r).append(rec["R_final"])
            d_arms[f"{s}/{arm}"] = {"runner_fires": len(run_r), "runner_kept3": sum(1 for r in run_r if r >= TAIL_R - _EPS),
                                    "runner_mean": _mean(run_r), "rest_n": len(rest_r), "rest_mean": _mean(rest_r)}
    # the grid's hold-type cells on runners too (stop x none x exit) at the final mark
    for s in STOPS:
        for ex in ("none", "trail_max10_20", "trail_sma10", "trail_sma20", "sma50_1x", "ema65_1x", "sma21_2x"):
            run_r, rest_r = [], []
            for row in rows["recorded"]:
                st = row["stops"][s]
                if st["killed"] or st["d0_abstain"]:
                    continue
                Kf = min(WINDOW, row["n_avail"])
                if Kf <= 0:
                    continue
                fp = row["fp"].get((s, "none"))
                stt, R, kind, ev = p3_grid.cell_r(row, st, fp, row["ex"][ex], Kf)
                if stt == "scored":
                    (run_r if row["id"] in runner_ids else rest_r).append(gap_charged(row, st, kind, ev, R))
            d_arms[f"grid:{s}/none/{ex}"] = {"runner_fires": len(run_r), "runner_kept3": sum(1 for r in run_r if r >= TAIL_R - _EPS),
                                             "runner_mean": _mean(run_r), "rest_n": len(rest_r), "rest_mean": _mean(rest_r)}
    summary["D_big_winners"] = {"stats": dict(rstats), "runners": {f"{k[0]}|{k[1]}": v for k, v in runners.items()}, "arms": d_arms}
    top = sorted(d_arms.items(), key=lambda kv: (-kv[1]["runner_kept3"], -(kv[1]["rest_mean"] or -9)))[:12]
    for k, v in top:
        print(f"   D arm {k:40s} runner fires {v['runner_fires']:3d} kept>=3R {v['runner_kept3']:3d} runner mean {v['runner_mean']} | rest n {v['rest_n']} mean {v['rest_mean']}")

    # ── E: named cases ──
    E = {}
    for (tkr, ep) in NAMED:
        ex_date, ex_min = NAMED_EXIT[(tkr, ep)]
        dft = daily.get(tkr, {})
        eb = dft.get(ep)
        last = dft.get(LAST_SESSION) or dft[max(dft)]
        case = {"ep_close": eb["close"], "ep_high": eb["high_price"], "ep_low": eb["low_price"], "close_09_25": last["close"],
                "our_exit": (str(ex_date), ex_min), "fires": []}
        for row in rows["recorded"]:
            if row["ticker"] != tkr or row["ep_date"] != ep:
                continue
            fm = row["fire_minute"]
            after_exit = row["fire_date"] > ex_date or (row["fire_date"] == ex_date and fm is not None and fm > ex_min)
            fr = {"rung": row["rung"], "fire_date": str(row["fire_date"]), "session": row["session_idx"],
                  "fire_minute_et": None if fm is None else f"{fm // 60:02d}:{fm % 60:02d}", "resolution": row["resolution"],
                  "entry": round(row["entry"], 2), "stop": round(row["stops"]["incumbent"]["level"], 2) if not row["stops"]["incumbent"]["killed"] else None,
                  "stop_width_pct": round(row["stops"]["incumbent"]["width_pct"], 2) if not row["stops"]["incumbent"]["killed"] else None,
                  "adr_dollar": round(row["adr"], 2), "after_our_exit": after_exit, "elapsed": row["elapsed"], "arms": {}}
            st = row["stops"]["incumbent"]
            if not st["killed"] and not st["d0_abstain"]:
                fp = row["fp"][("incumbent", "none")]
                Kf = min(WINDOW, row["n_avail"])
                for ex in ("none", "trail_max10_20"):
                    vals = {}
                    for K in (10, 20, Kf):
                        if row["elapsed"] >= K:
                            stt, R, kind, ev = p3_grid.cell_r(row, st, fp, row["ex"][ex], K)
                            vals[f"s{K}" if K in (10, 20) else "final"] = (round(R, 2), kind, ev) if stt == "scored" else stt
                    fr["arms"][f"incumbent/{ex}"] = vals
                # widest ADR stop, no target, hold + trail max
                for s in ("adr_100",):
                    st2 = row["stops"][s]
                    if not st2["killed"]:
                        fp2 = row["fp"][(s, "none")]
                        for ex in ("none", "trail_max10_20", "sma50_1x"):
                            vals = {}
                            for K in (10, 20):
                                if row["elapsed"] >= K:
                                    stt, R, kind, ev = p3_grid.cell_r(row, st2, fp2, row["ex"][ex], K)
                                    vals[f"s{K}"] = (round(R, 2), kind, ev) if stt == "scored" else stt
                            fr["arms"][f"{s}/{ex}"] = vals
                for s in MGMT_STOPS:
                    for arm in MGMT_ARMS:
                        rec = per_row.get((row["id"], s, arm))
                        if rec is None:
                            continue
                        fr["arms"][f"{s}/{arm}"] = {**{f"s{K}": (round(rec["R"][K], 2), rec["kind"][K]) for K in rec["R"]},
                                                    "final": (round(rec["R_final"], 2), rec.get("final_kind")) if rec.get("R_final") is not None else None,
                                                    "partial": rec["partial"], "abstain": rec.get("abstain")}
                # the entry-edge read
                d0 = st["d0_bars"]
                fr["plus2adr_before_minus1adr_s10"] = {b: walk_fire(row, row["entry"], row["stops"]["adr_100"]["d0_bars"], 10, b)
                                                       for b in ("pess", "opt")} if row["elapsed"] >= 10 and not row["stops"]["adr_100"]["killed"] else None
                # the path: max high / close through s20 in R (incumbent stop)
                highs = row["_sh"][:WINDOW]
                fr["max_high_r_incumbent"] = round((max(highs) - row["entry"]) / st["risk"], 2) if highs else None
                fr["close_09_25_r_incumbent"] = round((last["close"] - row["entry"]) / st["risk"], 2)
                fr["close_09_25_pct_from_entry"] = round(100 * (last["close"] / row["entry"] - 1), 1)
            case["fires"].append(fr)
        E[f"{tkr}|{ep}"] = case
        print(f"E {tkr} {ep}: EP close {eb['close']}, 09-25 close {last['close']}; fires {len(case['fires'])}")
        for fr in case["fires"]:
            print(f"    {fr['rung']:20s} {fr['fire_date']} s{fr['session']} {fr['fire_minute_et']} entry {fr['entry']} stop {fr['stop']} ({fr['stop_width_pct']}%) "
                  f"after_exit={fr['after_our_exit']} max_high {fr.get('max_high_r_incumbent')}R close09-25 {fr.get('close_09_25_r_incumbent')}R "
                  f"({fr.get('close_09_25_pct_from_entry')}%) inc/none {fr['arms'].get('incumbent/none')} inc/trail {fr['arms'].get('incumbent/trail_max10_20')} "
                  f"M1t_orb2@inc {fr['arms'].get('incumbent/M1t_orb2')} +2ADR {fr.get('plus2adr_before_minus1adr_s10')}")
    summary["E_named_cases"] = E

    with open(HERE / "events.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(events[0].keys()))
        w.writeheader(); w.writerows(events)
    (HERE / "summary.json").write_text(json.dumps(summary, indent=1, default=str))
    print("wrote summary.json, cells.tsv, events.csv")


if __name__ == "__main__":
    {"reproduce": phase_reproduce, "replay": phase_replay, "analyze": phase_analyze}[sys.argv[1]]()
