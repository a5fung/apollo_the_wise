"""#327 — the FREE hypothesis tests on the 277 real EPs (2026-09-27, Sunday build slot). $0. Worked ENTIRELY from
this folder's captured files (+ ONE read-only SELECT captured to rank_shadow.tsv for H5). No prod write, no new
bars, no toggle, no table, no deploy, no PLAN.md line, no live code touched.

═══════════════════════════ STEP 0 — POPULATION GATE (phase `gate`; HALT on any mismatch) ═══════════════════════════
Population = the rerun's 277 live-source mi_ep_alerts campaigns 2026-05-01 -> 09-11 (gate.sql / gate_out.txt),
re-derived from the files THIS probe loads (alerts.tsv, campaigns.tsv, fires.tsv):
    ERA A (alert_date < 2026-08-22): 261 campaigns / 243 names / HIGH 184 · MODERATE 66 · other 11
    ERA B (alert_date >= 08-22):      16 / 16 / HIGH 14 · MODERATE 2
    ALL:                             277 / 256;  fires.tsv 632 first-attempt fires (ERA A 595, ERA B 37)
Extra gate line for H4: campaigns_era_c.tsv (545p3) joins ALL 261 ERA A campaigns; on ERA A the era-C verdict is
    136 admit / 81 reject / 44 undecided — the "142 admit" in the task counts the 6 ERA B campaigns of 08-27/28
    (CHRN, CRWD, DG, OKTA, VEEV, SOLS), all admitted. 44 undecided are reported separately, never pooled.
ANCHORS (phase `anchor`, printed before any test; a miss is a HALT):
  (A) bf.walk_campaign (the 09-01 walker) with the horizon patched to 09-25 on rerun's loaders reproduces the 609
      replayed rows of fires.tsv on (rung, fire_date, fire_minute, entry, stop) with 0 drift; the 23 lane-recorded
      rows are taken as-is (no minute bars) and said so.
  (B) reentry.settle_attempt with the lane's OWN stop reproduces reentry_rows.tsv attempt 1 / incumbent on BOTH
      arms for all 632 (status, outcome, gap-charged R) with 0 drift.
  (C) this probe's H13 walker in rule=touch reproduces the same 632 attempt-1 rows (both arms) with 0 drift — the
      close-based rules are the SAME walk with a different exit test.
  (D) this probe's volume-carrying 5-min aggregator equals the lane's to_rth_5min on o/h/l/c for every session.

═══════════════════════════ PRE-REGISTRATION (written BEFORE any result was computed) ═══════════════════════════
SPLIT (as loaded): DISCOVERY = ERA A alerts <= 2026-08-14: 250 campaigns / 573 first fires. HELD-OUT A = ERA A
  alerts 08-15..08-21: 11 campaigns / 22 fires — ONE calendar week (AMLX ARGX BULL CBRS MRNA MRVL RARE SCSC TEM
  TWST UUUU); a week-block test cannot run inside it, it confirms DIRECTION only. ERA B = 16 / 37 fires, 23 of
  them lane-recorded with NO minute bars -> blind for H1c, H3, H12 and H13's volume override (counted per test).
MINIMUM HELD-OUT n: a held-out part with fewer than 8 readable fires (campaigns for H5/H12) reads "can't tell",
  never "fails". Below that the sign is printed but does not decide.
A RESULT COUNTS ("holds") only if, on DISCOVERY: the primary statistic is in the predicted direction, it survives
  dropping the best TWO NAMES (by ticker), the week-block permutation p < 0.05 (2000 draws, seed 327), AND the
  fillable-entry version (next 5-min bar's open + 5 bps on entry and on every exit fill) agrees in sign; AND the
  sign is the same on BOTH held-out parts (HELD-OUT A and ERA B, each >= 8 readable, else "can't tell").
  The recorded (5-min-close) entry is always reported BESIDE the fillable one, never instead.
PRIMARY MEASURE (his goal: catch big winners while limiting losses): the per-fire DIFFERENCE against the lane's
  current behaviour (its own stop + the trail arm: close below max(SMA10, SMA20)) on the SAME fires, gap-through
  stops charged at the open; plus TAIL RETENTION — of his 4 labelled EPs in the 277 (PLTR 08-04, TEAM 08-07,
  HTFL 08-14, MRNA 08-19; read from shared.operator_labelled_eps) and the rerun's 7 big-winner EPs (summary.json
  D_big_winners, never hand-listed), how many campaigns end >= 3R on any first fire — and the WORST single loss.
  A mean above zero alone is never the bar.
PERMUTATION: paired per-fire differences -> sign-flip WHOLE ISO-week blocks of the fire date; two-group reads
  (fire vs control, early vs late, admit vs reject, tercile vs tercile) -> shuffle the labels WITHIN each week.
DRAWS (every cell judged against a bar; per-pattern splits are shown, not counted):
  H2 4 (one per pattern) · H1b 3 (k = 0.5 / 0.75 / 1.0 x post-gap range, pooled) · H1c 3 (first-30-min low,
  first-60-min low, age terciles) · H3 3 (fire-time early vs late; reclaim/undercut bar volume; reclaim bar vs
  session-mean volume terciles) · H4 2 (1xADR low-reclaim trail; the lane's own cell) · H5 10 features ·
  H12 2 (trail, none arms) · H13 8 (2 levels x 4 close rules, M-none arm)  = 35 DRAWS.
NOISE BAND: 0.05 x 35 = 1.75 expected false clears -> <= 2 draws clearing anywhere is NOISE; >= 5 clearing on
  ONE mechanism is a family. Declared before running.
THE TESTS:
  H2 (gates the rest) — is the reclaim patterns' "+6 pts better than a random session" a volatility-timing
     artefact? (i) The rerun's ORIGINAL barriers (pre-EP ADR$: +2/-1) with the -1-FIRST rate reported beside the
     +2-first rate (an artefact raises both; an edge raises only +2). (ii) Barriers SCALED to the trailing
     3-session range Y = mean(high-low) over post-EP sessions max(1, s-2)..s (s = the entry session; floored at
     session 1, never the EP day; the same window for fires and controls; sensitivity: the fire session's range
     through the fire bar). Fires with >= 10 sessions after them vs every non-fire session of the same campaign
     windows entered at the close; outcome by session 10, pess (stop-first) primary, opt beside. Pass = +2-first
     gap >= +5 pts on discovery for the low and close reclaim, with the -1-first gap under half the +2 gap.
  H1b — stop = entry - k x R_post, R_post = mean(high-low) of the last <= 3 COMPLETED post-gap sessions known at
     the fire (the EP day counts as session 0 — post-gap, pre-fire), k in {0.5, 0.75, 1.0}; settled through the
     lane's compute_settlement (trail arm primary, none beside); diff vs the lane's own stop AND vs 1xADR pre-EP.
  H1c — (c1) stop at the fire session's first-N-minute low (N = 30, 60) on fires after minute N; (c2) age of the
     stop-defining low: the lane's stop price located among the fire session's 5-min lows before the fire bar
     (not found => an earlier session's low => oldest); terciles of age; oldest vs youngest on the lane's own
     arm: mean R and the share stopped within 2 sessions.
  H3 — (a) fire time: opening bar (09:30) / 09:35-09:59 / 10:00+; late vs early on the lane's arm and at 1xADR;
     (b) volume from minute.tsv.gz column v: reclaim bar volume / defining-low bar volume (same session; >= 1 vs
     < 1) and reclaim bar volume / mean of the session's earlier 5-min bars (terciles, top vs bottom).
  H4 — reentry_rows attempt 1: 1xADR ep_low_reclaim trail and the lane's own cell, on ERA A campaigns today's
     rules ADMIT (136) vs REJECT (81), undecided (44) separate; admitted-only by month; if admitted-only reads
     like ERA A overall (and unlike ERA B) the era split is tape/time, not the 08-22 rule.
  H5 — per-campaign outcome = max high over sessions 1-15 above the EP close in ADR$ (censored where fewer
     sessions exist, flagged) plus his labels; features (closed list): ext_xadr_eod, ext_xadr_pregap,
     tightness_pct_eod, composite_rank_eod, open_range_position, expct_scheduled, expct_looking, expct_beat,
     catalyst_type, tier. Spearman / class means; top vs bottom third runner share (>= 5 ADR). IN-SAMPLE on
     discovery by construction — only the held-out sign can count; discovery p is never a "holds".
  H12 (operator) — a 620 turn (qualified_620_crosses: MACD(6,20)<0 cross, basing <= 0.4 ADR over 8 buckets, hook)
     within k = 0.5 x ADR$ of ANY pivot on this FIXED list, computed from daily.tsv and known at the session's
     open: EP-day low; EP-day close; pre-EP base edge = max high of the 20 sessions before the EP day, and of the
     60; completed post-EP swing low = session j (1 <= j <= s-2) whose low is below both neighbours' lows (the EP
     day is j = 0's left neighbour); SMA10 and SMA20 of closes through session s-1 when RISING (above the value
     three sessions earlier). Stop = the session's low so far through the cross bar (the lane's basis; a cross
     closing at that low tries the next). First such fire per campaign over sessions 1-20; sessions without
     minutes are blind (counted). Per campaign vs the lane's FIRST fire (any pattern, own stop, trail) on the same
     campaigns; 1xADR stop beside. TEAM 08-07 (day 0, no warm-up bars on disk) and 08-10 hand-walked.
  H13 (operator) — exit on a DAILY CLOSE below the level (the lane's stop; the 10-day SMA through the prior
     session, inapplicable when it sits at/above the entry — counted), with an intraday override only on a violent
     break: (a) none, (b) > 0.5 x ADR$ through the level, (c) > 1.0 x ADR$, (d) a 5-min bar closing below the
     level on volume > 3x the session's earlier 5-min mean (>= 3 earlier bars; sessions without minutes are blind
     for the override, counted). M-none arm primary (isolates the stop), trail beside. Per fire vs the TOUCH stop
     at the same level, in that level's R; the SMA10 rows also in the lane's R. Reported beside the mean: the
     worst single loss and the count of losses beyond -1.5R — a close stop can lose far more than 1R on a slice.
EXPECTED BEFORE RUNNING (stated so a surprise is visible): H2 partly artefact (the -1-first rate also elevated,
  the scaled gap smaller than +6); H1b about as good as 1xADR (same money, different yardstick); H1c and H3
  weak or null; H4 "tape/time"; H5 can't tell (held-out too thin); H12 fires on few campaigns, TEAM day-0 turn
  qualifies but sits outside the lane; H13 close rules lose more per loss than they save.

Usage:  python3 hyptests.py gate | anchor | run | report        (run ONCE; the report reads the row files)
Outputs: hyp_gate_out.txt, hyp_anchor_out.txt, hyp_rows_*.tsv, hyp_report.txt, hyp_summary.json
"""
from __future__ import annotations

import csv
import json
import math
import random
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
for p in (REPO, REPO / "scripts" / "probes", REPO / "scripts" / "probes" / "_327_block5", HERE):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import rerun                                      # noqa: E402  loaders, read_tsv, _f
import reentry                                    # noqa: E402  settle_attempt, make_ctx, load_campaigns, load_runners
import _562_backfill_replay as bf                 # noqa: E402  the 09-01 walker
import p2_probe                                   # noqa: E402  first_passage / at_checkpoint
from agents.market_intelligence.delayed_entry_shadow import (   # noqa: E402  real code
    SETTLE_HOLD_SESSIONS, WARMUP_SESSIONS_620, _trading_days, compute_ep_adr_dollar, macd_620,
    qualified_620_crosses, sma_trail_line, to_rth_5min, BASING_BARS, BASING_BAND_ADR, HOOK_SHORT, HOOK_LONG,
    MIN_CROSS_IDX,
)
from shared.operator_labelled_eps import OPERATOR_LABELLED_EPS   # noqa: E402

HORIZON = date(2026, 9, 25)
ERA_SPLIT = date(2026, 8, 22)
DISC_END = date(2026, 8, 14)
SEED = 327
N_PERM = 2000
BPS = 0.0005
MIN_HELDOUT = 8
TAIL_R = 3.0
PATTERNS = rerun.PATTERNS
K_POST = (0.5, 0.75, 1.0)
H1C_N = (30, 60)
H13_RULES = ("close", "close_adr050", "close_adr100", "close_vol3x")
PIVOT_K = 0.5
N_DRAWS = 4 + 3 + 3 + 3 + 2 + 10 + 2 + 8
NOISE_MAX, FAMILY_MIN = 2, 5
_EPS = 1e-9
STOP, TARGET, OPEN, ABSTAIN = "stop", "target", "open", "abstain"


def _f(v):
    return rerun._f(v)


def split_of(ep_date, era):
    if era == "B":
        return "B"
    return "DISC" if ep_date <= DISC_END else "HOA"


def week_of(d):
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def mean(v):
    return statistics.mean(v) if v else None


def fmt(x, f="{:+.2f}"):
    return "—" if x is None else f.format(x)


# ── loaders ───────────────────────────────────────────────────────────────────────────────────────────

def to_rth_5min_v(raw, session_day):
    """The lane's to_rth_5min plus summed volume per bucket (the lane drops v — G2). Anchored (D)."""
    out = to_rth_5min(raw, session_day)
    vol = defaultdict(float)
    for b in raw:
        m = b["m"]
        b5 = m - ((m - 570) % 5)
        vol[b5] += b.get("v") or 0.0
    for b in out:
        b["v"] = vol.get(b["m"], 0.0)
    return out


def load_reentry_attempt1():
    by = {}
    for r in rerun.read_tsv(HERE / "reentry_rows.tsv"):
        if r["attempt"] != "1":
            continue
        by[(r["ticker"], r["ep_date"], r["rung"], r["stop"], r["arm"])] = {
            "status": r["status"], "outcome": r["outcome"], "r": _f(r["r"]), "r_gap": _f(r["r_gap"]),
            "stop_w": _f(r["stop_w"]), "stop_day": r["stop_day"], "d0_kind": r["d0_kind"], "mfe_r": _f(r["mfe_r"])}
    return by


def load_era_c():
    out = {}
    for r in rerun.read_tsv(REPO / "scripts" / "ep_replay_data" / "campaigns_era_c.tsv"):
        out[(r["ticker"], r["alert_date"])] = r["admit"]
    return out


def load_rank_shadow():
    out = {}
    for r in rerun.read_tsv(HERE / "rank_shadow.tsv"):
        if not r.get("alert_date") or r["ticker"].startswith("("):
            continue
        out[(r["ticker"], r["alert_date"])] = r
    return out


def load_everything():
    alerts = rerun.load_alerts()
    camps = reentry.load_campaigns()
    fires = rerun.load_fires()
    daily = rerun.load_daily()
    raw, dropped = rerun.load_minutes_raw()
    min5 = {k: to_rth_5min_v(v, k[1]) for k, v in raw.items()}
    runners = reentry.load_runners()
    keys277 = {(a["ticker"], a["ep_date"].isoformat()) for a in alerts}
    labelled = {(e.ticker, e.alert_date) for e in OPERATOR_LABELLED_EPS if (e.ticker, e.alert_date) in keys277}
    era_of = {(a["ticker"], a["ep_date"]): a["era"] for a in alerts}
    for f in fires:
        f["split"] = split_of(f["ep_date"], f["era"])
        f["week"] = week_of(f["fire_date"])
    return {"alerts": alerts, "camps": camps, "fires": fires, "daily": daily, "raw": raw, "dropped": dropped,
            "min5": min5, "runners": runners, "labelled": labelled, "era_of": era_of}


# ── phase: gate ───────────────────────────────────────────────────────────────────────────────────────

def phase_gate():
    alerts = rerun.load_alerts()
    camps = reentry.load_campaigns()
    fires = rerun.load_fires()
    gate = defaultdict(dict)
    for r in rerun.read_tsv(HERE / "gate_out.txt"):
        gate[r["era"]][r["k"]] = r["v"]
    lines, ok = [], True

    def chk(cond, text):
        nonlocal ok
        ok &= bool(cond)
        lines.append(("ok  " if cond else "MISMATCH ") + text)

    for era in ("A", "B"):
        rows = [a for a in alerts if a["era"] == era]
        chk(all((a["ep_date"] < ERA_SPLIT) == (era == "A") for a in rows), f"ERA {era} era label == alert_date rule")
        tiers = Counter(a["tier"] for a in rows)
        got = {"campaigns": len(rows), "names": len({a["ticker"] for a in rows}), "tier_HIGH": tiers.get("HIGH", 0),
               "tier_MODERATE": tiers.get("MODERATE", 0), "tier_none": tiers.get("none", 0)}
        for k, v in got.items():
            g = gate[era].get(k, "0")
            chk(str(v) == g, f"ERA {era} {k:14s} loaded={v} gate_out={g}")
        chk(str(reentry._sql_median([a["prior_close"] for a in rows])) == gate[era]["median_prior_close"],
            f"ERA {era} median_prior_close {reentry._sql_median([a['prior_close'] for a in rows])} gate_out={gate[era]['median_prior_close']}")
    chk(str(len(alerts)) == gate["ALL"]["campaigns"] and str(len({a['ticker'] for a in alerts})) == gate["ALL"]["names"],
        f"ALL campaigns {len(alerts)} / names {len({a['ticker'] for a in alerts})} vs gate_out {gate['ALL']['campaigns']} / {gate['ALL']['names']}")
    ak = {(a["ticker"], a["ep_date"]) for a in alerts}
    chk(set(camps) == ak, f"campaigns.tsv keys == alerts.tsv keys ({len(camps)} vs {len(ak)})")
    fk = {(f["ticker"], f["ep_date"]) for f in fires}
    nA, nB = sum(1 for f in fires if f["era"] == "A"), sum(1 for f in fires if f["era"] == "B")
    chk(fk <= ak and len(fires) == 632 and nA == 595 and nB == 37,
        f"fires.tsv: {len(fires)} first fires on {len(fk)} campaigns (ERA A {nA}, ERA B {nB}); all in the 277")
    lane = [f for f in fires if f["source"] == "lane_recorded"]
    chk(len(lane) == 23, f"lane-recorded first fires (no minute bars) = {len(lane)}")
    for tk in (("TEAM", date(2026, 8, 7)), ("MRNA", date(2026, 8, 19)), ("PLTR", date(2026, 8, 4)), ("HTFL", date(2026, 8, 14))):
        chk(tk in ak, f"named campaign present: {tk[0]} {tk[1]}")
    # split sizes
    A = [a for a in alerts if a["era"] == "A"]
    disc = [a for a in A if a["ep_date"] <= DISC_END]
    hoa = [a for a in A if a["ep_date"] > DISC_END]
    lines.append(f"    SPLIT: DISCOVERY {len(disc)} campaigns / {sum(1 for f in fires if f['split'] == 'DISC') if 'split' in fires[0] else sum(1 for f in fires if f['era']=='A' and f['ep_date'] <= DISC_END)} fires; "
                 f"HELD-OUT A {len(hoa)} / {sum(1 for f in fires if f['era']=='A' and f['ep_date'] > DISC_END)} fires "
                 f"(weeks {sorted({week_of(a['ep_date']) for a in hoa})}: {sorted(a['ticker'] for a in hoa)}); "
                 f"ERA B {sum(1 for a in alerts if a['era']=='B')} / {nB} fires ({len(lane)} lane-recorded)")
    # era-C join for H4
    ec = load_era_c()
    ea = {k: ec.get((k[0], k[1].isoformat())) for k in ak if k[1] < ERA_SPLIT}
    cnt = Counter(v for v in ea.values())
    chk(None not in cnt and cnt.get("admit") == 136 and cnt.get("reject") == 81 and cnt.get("abstain_float_band_straddles_bar") == 44,
        f"era-C verdict joins all 261 ERA A campaigns: {dict(cnt)} (the task's 142 admits include 6 ERA B campaigns of 08-27/28)")
    eb = {k: ec.get((k[0], k[1].isoformat())) for k in ak if k[1] >= ERA_SPLIT}
    lines.append(f"    era-C verdicts on ERA B campaigns: {Counter(v for v in eb.values())}")
    rs = load_rank_shadow()
    chk(set(rs) == {(k[0], k[1].isoformat()) for k in ak}, f"rank_shadow.tsv keys == the 277 ({len(rs)})")
    txt = "\n".join(lines) + f"\n\nGATE {'PASSED' if ok else 'FAILED — HALT'}\n"
    (HERE / "hyp_gate_out.txt").write_text(txt)
    print(txt)
    if not ok:
        sys.exit(1)


# ── the settlement instrument (the lane's compute_settlement via reentry.settle_attempt) ───────────────

def gap_charge(ctx, res, entry, stop, arm):
    """The rerun's convention: a stop at session >= 1 whose session opened below the stop fills at the open."""
    outcome = res["outcome"] if arm == "none" else res["outcome_trail"]
    r = res["realized_r"] if arm == "none" else res["realized_r_trail"]
    gap = False
    if outcome == "stop":
        sidx = res["stop_session_idx"]
        if sidx and sidx >= 1:
            sd = res["_sessions"][sidx - 1]
            o = (ctx["bars"].get(sd) or {}).get("open_price")
            if o is not None and o < stop:
                r = round((o - entry) / (entry - stop), 4)
                gap = True
    return outcome, r, gap


def settle_first(ctx, min5, f, entry, stop, fm, fire_date, d0=None, post5_override=None):
    """One first attempt through the lane's own compute_settlement (reentry.settle_attempt) at (entry, stop);
    returns {status, none:(outcome,r,gap), trail:(...), mfe, mae, stop_idx, marked_at}. `post5_override`
    replaces the day-0 post-fire bars (used for the fillable entry, whose walk starts at the fill bucket)."""
    if stop is None or entry is None or stop >= entry or stop <= 0:
        return {"status": "killed"}
    if post5_override is None:
        res = reentry.settle_attempt(ctx, min5, entry, stop, fire_date, fm, HORIZON, d0_cache=d0)
    else:
        res = reentry.settle_attempt(ctx, {(ctx["tkr"], fire_date): post5_override}, entry, stop, fire_date, fm, HORIZON, d0_cache=None)
    if res["status"] not in ("settled", "marked"):
        return {"status": "abstain", "why": res.get("reason")}
    out = {"status": res["status"], "mfe": res.get("mfe_r"), "mae": res.get("mae_r"),
           "stop_idx": res.get("stop_session_idx"), "marked_at": res.get("marked_at")}
    for arm in ("none", "trail"):
        out[arm] = gap_charge(ctx, res, entry, stop, arm)
    return out


def slip_r(entry, stop, r, gap_r):
    """Apply the 5 bps exit slippage to a settled R: exit price p = entry + R x risk -> p x (1 - bps)."""
    risk = entry - stop
    p = entry + r * risk
    return round((p * (1 - BPS) - entry) / risk, 4)


def fill_entry(f, min5, ctx):
    """Fillable entry: the NEXT 5-min bucket's open x (1 + 5 bps). Minute fire: first bucket with m >= fm + 5 on
    the fire day (its bars from that bucket on are the day-0 walk); a 15:55 fire fills at the next session's
    open (day 0 = that session, daily grade). Daily-grade level fire: max(level, day open). Lane-recorded
    fires (no bars) -> None, counted."""
    fm = f["fire_minute"]
    bars = min5.get((ctx["tkr"], f["fire_date"]))
    if fm is None:
        fb = ctx["bars"].get(f["fire_date"]) or {}
        o = fb.get("open_price")
        if o is None:
            return None
        e = max(f["entry"], o) * (1 + BPS)
        return {"entry": e, "fire_date": f["fire_date"], "fm": None, "post5": None, "kind": "level_open"}
    if not bars:
        return None
    nxt = [b for b in bars if b["m"] >= fm + 5]
    if nxt:
        e = nxt[0]["o"] * (1 + BPS)
        return {"entry": e, "fire_date": f["fire_date"], "fm": nxt[0]["m"] - 1, "post5": nxt, "kind": "next_bucket"}
    sess = _trading_days(f["fire_date"] + timedelta(days=1), HORIZON)
    if not sess:
        return None
    nb = ctx["bars"].get(sess[0]) or {}
    if nb.get("open_price") is None:
        return None
    return {"entry": nb["open_price"] * (1 + BPS), "fire_date": sess[0], "fm": None, "post5": None, "kind": "next_session_open"}


def settle_both(ctx, min5, f, stop_fn, d0):
    """Recorded AND fillable settlements for one fire under a stop rule stop_fn(entry) -> stop price."""
    out = {}
    e = f["entry"]
    s = stop_fn(e)
    out["rec"] = settle_first(ctx, min5, f, e, s, f["fire_minute"], f["fire_date"], d0=d0)
    out["rec"]["stop"] = s
    fe = fill_entry(f, min5, ctx)
    if fe is None:
        out["fill"] = {"status": "no_fill"}
    else:
        s2 = stop_fn(fe["entry"])
        r = settle_first(ctx, min5, f, fe["entry"], s2, fe["fm"], fe["fire_date"], d0=None, post5_override=fe["post5"])
        if r["status"] in ("settled", "marked"):
            for arm in ("none", "trail"):
                oc, rr, g = r[arm]
                r[arm] = (oc, slip_r(fe["entry"], s2, rr, g), g)
        r["stop"], r["entry"], r["kind"] = s2, fe["entry"], fe["kind"]
        out["fill"] = r
    return out


# ── the H13 walker (own code; anchored on rule=touch against the lane) ─────────────────────────────────

def sma_n(closes, n):
    if len(closes) < n:
        return None
    return sum(closes[-n:]) / n


def walk_h13(ctx, min5, entry, fm, fire_date, level0, rule, arm, adr, level_kind="fixed", d0=None, post5_override=None,
             fill_bps=0.0):
    """Walk one first attempt from (entry, fire_date, fm) under an exit rule:
       touch        — low <= L exits at L (open if the session opened below L)             [= the lane]
       close        — exits at the CLOSE of the first session closing below L (day 0 incl.)
       close_adr050 / close_adr100 — plus an intraday exit when low <= L - x*ADR$ (at that price, or the open)
       close_vol3x  — plus an intraday exit at a 5-min bar closing below L on volume > 3x the session's earlier
                      5-min mean (>= 3 earlier bars); sessions without minutes are blind for the override
       level_kind 'fixed' -> L = level0; 'sma10' -> L(session) = SMA10 of closes through the PRIOR session.
       arm 'none' = stop else session-20 close; 'trail' = also a close below max(SMA10, SMA20).
       Returns status/outcome/r (in the level's R at the fire)/exit_idx/mfe/mae/blind/marked_at."""
    bars = ctx["bars"]
    fb = bars.get(fire_date) or {}
    f_hi, f_lo, f_c, f_o = fb.get("high_price"), fb.get("low_price"), fb.get("close"), fb.get("open_price")
    if f_hi is None or f_lo is None or f_c is None:
        return {"status": "abstain", "why": "missing_fire_day_bar"}
    closes_pre = [bars[d]["close"] for d in ctx["ordered"] if d < fire_date and bars[d]["close"] is not None]
    L0 = level0 if level_kind == "fixed" else sma_n(closes_pre, 10)
    if L0 is None:
        return {"status": "inapplicable", "why": "no_sma10"}
    if L0 >= entry or L0 <= 0:
        return {"status": "inapplicable", "why": "level_ge_entry"}
    risk = entry - L0
    x = {"close_adr050": 0.5, "close_adr100": 1.0}.get(rule)
    sessions = _trading_days(fire_date + timedelta(days=1), HORIZON)
    closes = list(closes_pre)
    mfe = mae = None
    blind = 0
    exit_px = exit_idx = outcome = None
    slip = (1 - fill_bps)

    def price_exit(p, idx, oc):
        nonlocal exit_px, exit_idx, outcome
        exit_px, exit_idx, outcome = p, idx, oc

    # ── day 0 ──
    L = L0
    day0_bars = None
    if fm is not None:
        if post5_override is not None:
            day0_bars = post5_override
        else:
            b5 = min5.get((ctx["tkr"], fire_date))
            if b5:
                day0_bars = [b for b in b5 if b["m"] > fm]
            elif d0 is not None:
                pb = reentry.day0_pseudo_bars(*d0)
                day0_bars = pb
    need_day0 = fm is not None and f_lo <= (L if rule == "touch" else (L - x * adr if x is not None else -1e18))
    if rule == "close_vol3x" and fm is not None:
        need_day0 = need_day0 or (f_lo < L)     # the override needs the bars whenever the day traded under L
    if fm is not None and need_day0 and day0_bars is None:
        if rule == "close_vol3x" and not (f_lo <= L - 1e18):
            blind += 1                           # override blind on day 0; the close rule still reads
        else:
            return {"status": "abstain", "why": "missing_day0_minutes"}
    if fm is not None and day0_bars is not None:
        all5 = min5.get((ctx["tkr"], fire_date)) or []
        pre_v = [b.get("v", 0.0) for b in all5 if b["m"] <= (fm if post5_override is None else fm)]
        for b in day0_bars:
            lo, hi, c = b["l"], b["h"], b["c"]
            mfe = hi if mfe is None else max(mfe, hi)
            mae = lo if mae is None else min(mae, lo)
            if rule == "touch" and lo <= L:
                price_exit(L, 0, "stop"); break
            if x is not None and lo <= L - x * adr:
                price_exit(L - x * adr, 0, "stop_violent"); break
            if rule == "close_vol3x" and "v" in b and c < L and len(pre_v) >= 3 and b["v"] > 3.0 * (sum(pre_v) / len(pre_v)):
                price_exit(c, 0, "stop_volume"); break
            pre_v.append(b.get("v", 0.0))
    elif fm is None:
        mfe, mae = f_hi, f_lo
        if rule == "touch" and f_lo <= L:
            price_exit(L, 0, "stop")
        elif x is not None and f_lo <= L - x * adr:
            price_exit(L - x * adr, 0, "stop_violent")
    else:
        mfe, mae = (f_hi, f_lo) if mfe is None else (mfe, mae)
    closes.append(f_c)
    if outcome is None and rule != "touch" and f_c < L and (fm is not None or post5_override is not None or True):
        # a fill at the next session's open (fm None, post5 None, kind next_session_open) has no day-0 close check
        price_exit(f_c, 0, "stop_close")
    if outcome is None and arm == "trail":
        line = sma_trail_line(closes)
        if line is not None and f_c < line:
            price_exit(f_c, 0, "trail_exit")
    # ── sessions 1..20 ──
    if outcome is None:
        for i, d in enumerate(sessions, start=1):
            if i > SETTLE_HOLD_SESSIONS:
                break
            b = bars.get(d) or {}
            hi, lo, c, o = b.get("high_price"), b.get("low_price"), b.get("close"), b.get("open_price")
            if hi is None or lo is None or c is None:
                return {"status": "abstain", "why": f"missing_session:{d}"}
            if level_kind == "sma10":
                L = sma_n(closes, 10)
            mfe = max(mfe, hi) if mfe is not None else hi
            mae = min(mae, lo) if mae is not None else lo
            if rule == "touch" and lo <= L:
                price_exit(o if (o is not None and o < L) else L, i, "stop"); closes.append(c); break
            if x is not None and lo <= L - x * adr:
                lvl = L - x * adr
                price_exit(o if (o is not None and o < lvl) else lvl, i, "stop_violent"); closes.append(c); break
            if rule == "close_vol3x":
                b5 = min5.get((ctx["tkr"], d))
                if not b5:
                    if lo < L:
                        blind += 1
                else:
                    pv = []
                    hit = False
                    for bb in b5:
                        if bb["c"] < L and len(pv) >= 3 and bb["v"] > 3.0 * (sum(pv) / len(pv)):
                            price_exit(bb["c"], i, "stop_volume"); hit = True; break
                        pv.append(bb["v"])
                    if hit:
                        closes.append(c); break
            closes.append(c)
            if rule != "touch" and c < L:
                price_exit(c, i, "stop_close"); break
            if arm == "trail":
                line = sma_trail_line(closes)
                if line is not None and c < line:
                    price_exit(c, i, "trail_exit"); break
            if i == SETTLE_HOLD_SESSIONS:
                price_exit(c, i, "time_exit"); break
    status = "settled"
    marked_at = None
    if outcome is None:
        if not sessions or len(sessions) < SETTLE_HOLD_SESSIONS:
            last_i = len(sessions)
            last_c = bars[sessions[-1]]["close"] if sessions else f_c
            price_exit(last_c, last_i, "open"); status, marked_at = "marked", last_i
        else:
            return {"status": "abstain", "why": "window_open"}
    r = (exit_px * slip - entry) / risk
    return {"status": status, "outcome": outcome, "r": round(r, 4), "exit_idx": exit_idx, "blind": blind,
            "mfe": round((mfe - entry) / risk, 4) if mfe is not None else None,
            "mae": round((mae - entry) / risk, 4) if mae is not None else None, "marked_at": marked_at,
            "level0": L0, "risk": risk, "exit_px": exit_px}


# ── phase: anchor ─────────────────────────────────────────────────────────────────────────────────────

def phase_anchor():
    D = load_everything()
    out = []
    # (A) the 09-01 walker at the 09-25 horizon reproduces fires.tsv's 609 replayed rows
    bf.LAST_DATA_DAY = HORIZON
    plain5 = {k: to_rth_5min(v, k[1]) for k, v in D["raw"].items()}
    mine = Counter()
    unc = {k for k, c in D["camps"].items() if c["era"] == "B" and c["cov_sessions"] and c["cov_have"] < rerun.COVERAGE_MIN_FRAC * c["cov_sessions"]}
    extra_unc = 0
    for a in D["alerts"]:
        c = bf.walk_campaign(a, D["daily"], plain5, set())
        if (a["ticker"], a["ep_date"]) in unc:
            extra_unc += len(c["fires"])     # the rerun REPLACED these with the lane's recorded rows (pre-registered)
            continue
        for f in c["fires"]:
            mine[(a["ticker"], a["ep_date"].isoformat(), f["rung"], f["fire_date"].isoformat(), f["fire_minute"],
                  round(f["entry"], 6), round(f["stop"], 6))] += 1
    rec = Counter((f["ticker"], f["ep_date"].isoformat(), f["rung"], f["fire_date"].isoformat(), f["fire_minute"],
                   round(f["entry"], 6), round(f["stop"], 6)) for f in D["fires"] if f["source"] == "replay")
    common = sum((mine & rec).values())
    out.append(f"ANCHOR A — 09-01 walker @ horizon 09-25 on rerun's loaders: {sum(mine.values())} fires vs {sum(rec.values())} replayed rows in "
               f"fires.tsv; {common} match on (rung, fire_date, fire_minute, entry, stop); drift {sum((mine - rec).values()) + sum((rec - mine).values())}; "
               f"lane-recorded rows taken as-is: {sum(1 for f in D['fires'] if f['source'] == 'lane_recorded')} "
               f"(the walker's own {extra_unc} fires on the {len(unc)} uncovered ERA B campaigns were replaced by those rows in the rerun, as pre-registered)")
    okA = common == sum(rec.values()) == sum(mine.values())
    # (D) the volume aggregator == the lane's on o/h/l/c
    bad = 0
    for k, v in D["min5"].items():
        p = plain5[k]
        if len(p) != len(v) or any(abs(a["o"] - b["o"]) > 1e-9 or abs(a["h"] - b["h"]) > 1e-9 or abs(a["l"] - b["l"]) > 1e-9 or abs(a["c"] - b["c"]) > 1e-9 or a["m"] != b["m"] for a, b in zip(p, v)):
            bad += 1
    out.append(f"ANCHOR D — to_rth_5min_v vs the lane's to_rth_5min on o/h/l/c/m: {len(D['min5'])} sessions, {bad} differ")
    okD = bad == 0
    # (B) settle_first with the lane's own stop vs reentry_rows attempt 1 incumbent; (C) walk_h13 touch vs the same
    a1 = load_reentry_attempt1()
    cB, cC = Counter(), Counter()
    linesB, linesC = [], []
    for f in D["fires"]:
        ctx = reentry.make_ctx(f, D["daily"])
        d0 = (f["day0_resolved"], f["day0_post_low"], f["day0_post_high"]) if f["source"] == "lane_recorded" else None
        res = settle_first(ctx, D["min5"], f, f["entry"], f["stop"], f["fire_minute"], f["fire_date"], d0=d0)
        for arm in ("none", "trail"):
            ref = a1[(f["ticker"], f["ep_date"].isoformat(), f["rung"], "incumbent", arm)]
            if res["status"] in ("settled", "marked"):
                oc, r, g = res[arm]
                ok = ref["status"] == res["status"] and ref["outcome"] == oc and abs(ref["r_gap"] - r) < 1e-4
            else:
                ok = ref["status"] == "abstain"
            cB["match" if ok else "MISMATCH"] += 1
            if not ok and len(linesB) < 20:
                linesB.append(f"  B {f['ticker']} {f['ep_date']} {f['rung']} {arm}: mine {res.get('status')}/{res.get(arm)} vs rows {ref}")
            w = walk_h13(ctx, D["min5"], f["entry"], f["fire_minute"], f["fire_date"], f["stop"], "touch", arm, f["adr_dollar"] or 0.0, d0=d0)
            if w["status"] in ("settled", "marked"):
                # reentry labels a trail exit inside a sub-20-session window "marked" (its M-none arm was still
                # open); the walker settles the arm it walks. Readable + same outcome + same R is the anchor.
                ok2 = ref["status"] in ("settled", "marked") and ref["outcome"] == w["outcome"] and abs(ref["r_gap"] - w["r"]) < 1e-4
            else:
                ok2 = ref["status"] == "abstain"
            cC["match" if ok2 else "MISMATCH"] += 1
            if not ok2 and len(linesC) < 20:
                linesC.append(f"  C {f['ticker']} {f['ep_date']} {f['rung']} {arm}: walker {w} vs rows {ref}")
    out.append(f"ANCHOR B — settle_first (lane's compute_settlement) with the lane's own stop vs reentry_rows attempt 1 / incumbent, both arms: {dict(cB)}")
    out.extend(linesB)
    out.append(f"ANCHOR C — walk_h13 rule=touch vs the same rows, both arms: {dict(cC)}")
    out.extend(linesC)
    okB, okC = cB.get("MISMATCH", 0) == 0, cC.get("MISMATCH", 0) == 0
    txt = "\n".join(out) + f"\n\nANCHORS {'PASSED' if (okA and okB and okC and okD) else 'FAILED — HALT'}\n"
    (HERE / "hyp_anchor_out.txt").write_text(txt)
    print(txt)
    if not (okA and okB and okC and okD):
        sys.exit(1)


if __name__ == "__main__":
    ph = sys.argv[1]
    if ph == "gate":
        phase_gate()
    elif ph == "anchor":
        phase_anchor()
    else:
        import hyptests_run  # noqa: F401  the run/report phases live beside this file
        hyptests_run.main(ph)
