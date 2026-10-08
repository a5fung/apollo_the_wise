"""#327 H7 — a day-0 AFTERNOON re-entry after the opening shakeout (his TEAM 08-07 trade), sized as a $0 replay.
MEASUREMENT ONLY. Day 0 is OUTSIDE the lane by his 08-30 ruling and INSIDE the live R3 same-day re-entry ban
(shipped 05-17) — adopting anything here would reverse a live rule (CHANGE_PROCESS, his call alone). No prod
access, no writes outside this folder, no deploy, no commit. Worked entirely from this folder's captured files.

═════════════ THE BAR (verbatim, docs/analysis/327_hypotheses_2026-09-27.md §2 row H7, Test column) ═════════════
  "Pop: campaigns with full EP-day minute bars (212 of 261 ERA A; 15 of 16 ERA B), restricted to those whose day-0
   price broke the first 1-min bar's low. Measure: entry edge vs a day-0 control (every 5-min close after 10:30 on
   the same day), same-day stop rate, winner capture, TEAM reproduced within 15 min of 12:05. Pass: ≥ +5 pts ·
   n ≥ 100 on ≥ 60 names · survives drop-best-two · positive ex-May · ERA B same sign. Dark days reported as a
   count, never imputed."
  Trigger (same row, Fix column): "stretched + turning + basing after 10:30 ET, within reach of the EP-day open /
   opening-range low; stop = basing low floored at 0.5× ADR".

═════════════ PRE-REGISTRATION (written BEFORE any population result was computed) ═════════════
The ONLY thing looked at before writing this: TEAM 08-07 itself (the pre-declared n = 1 anchor) — its 1-min bars
11:00-12:30 and its qualified 620 cross. That look showed the frozen cross-bar CLOSE entry lands at the 11:40
bucket (complete 11:45, 20-25 min before his ~12:05 entry) and so FAILS the row's "TEAM reproduced within 15 min"
requirement, while a buy-stop at the cross bar's HIGH fills 12:00 at $143.90 (his $144.39 ~12:05-12:08). The
entry mechanics below were therefore CHOSEN TO REPRODUCE TEAM (n = 1); the cross-close entry is carried as the
pre-declared sensitivity, and every headline number is also shown WITHOUT TEAM.

POPULATION
  The 277 live-source mi_ep_alerts campaigns 2026-05-01 -> 09-11 (alerts.tsv; the 09-27 program's population).
  ERA A = alert_date < 2026-08-22 (261), ERA B = from 08-22 (16). NEVER pooled. In-sample part of ERA A (<= 08-14)
  and its held-out week (08-15..08-21) shown beside, never instead.
  Day-0 (EP-day) 1-min RTH bars: minute.tsv.gz, REPLACED (not appended) by sat_day0_minutes.tsv.gz for its 50 keys
  (the Saturday Polygon pull; old bars are a subset of new). Classes on the MERGED bars: full >= 300 RTH bars,
  thin 100-299 (complete per Polygon, a thinly traded name), DARK < 100 (the rerun's MIN_MINUTE_BARS rule, not
  lowered) — dark days are COUNTED, never imputed. Primary = full + thin; full-only shown beside. No volume is used
  anywhere (Polygon minute volumes differ from stored ones; the trigger has no volume leg).
  Opening range = the FIRST RTH 1-min bar of day 0 (the live MAGNA53 ORB bar); days whose first bar is after 09:31
  are flagged. SHAKEOUT = a later day-0 1-min low strictly below that bar's low. Restricted population = readable
  (not dark, ADR$ and EP-day daily bar present) campaigns with a shakeout.

TRIGGER (one per campaign, day 0 only; no warm-up seed exists on disk for day 0, so the 620 EMAs start at 09:30)
  A qualified 620 turn = qualified_620_crosses() from delayed_entry_shadow.py VERBATIM (MACD(6,20) < 0 crossing
  above its EMA-9 signal = stretched + turning; hook guard; basing = the prior 8 five-min buckets' range <= 0.4 x
  ADR$), on the EP day's own 5-min buckets, filtered IN THIS ORDER (each rejection counted):
   (1) "after 10:30": the cross bucket's label m >= 630 (10:30 ET) — stated explicitly, not left to MIN_CROSS_IDX;
   (2) the shakeout happened first: the first 1-min low below the ORB low is at or before the cross bucket's last
       minute (m + 4);
   (3) "within reach": the cross-bar close within 0.5 x ADR$ (the program's PIVOT_K band) of the EP-day OPEN
       (daily.tsv open_price) OR of the ORB low; which reference matched is recorded.
  basing low = min low of the 8 basing buckets AND the cross bucket.
  PRIMARY ENTRY (rule "bstop"): arm a buy-stop at the cross bucket's HIGH from the next minute (m + 5). Walk day-0
   1-min bars: a bar whose low <= basing low CANCELS the arm (tested first on a bar that does both — pess); a bar
   whose high >= the level FILLS at max(level, bar open). A cancel frees the next qualifying cross whose bucket
   completes after the cancel minute (crosses completing while an arm is live are skipped, counted). No fill by
   the last RTH bar = no fire (counted). First fill = the campaign's one fire.
  SENSITIVITY ENTRY (rule "close"): the first cross passing (1)-(3), entry = the cross bucket's close (the lane's
   own 620 convention), fire_minute = the bucket label.
  STOP = min(basing low, entry - 0.5 x ADR$) ("basing low floored at 0.5 x ADR"). Expected before running: the
   basing band is 0.4 ADR, so the 0.5 floor binds on nearly every fire — the stop is effectively entry - 0.5 ADR.
   The UNFLOORED basing-low stop (closest to his actual 141.51) is settled beside, descriptive only.
  ADR$ = campaigns.tsv adr_dollar (pre-EP, the program's yardstick).

PRIMARY MEASURE — "entry edge" = the 09-27 H2 instrument: from the entry, does price reach +2 x ADR$ before
  -1 x ADR$ by session 10 (p2_probe.first_passage + at_checkpoint, pess = stop first on a straddle; share of
  NON-abstaining walks, open walks in the denominator). FIRES AND CONTROLS BOTH walk the remainder of day 0 on its
  own intraday bars (fires: the fill bucket's later 1-min bars then later 5-min buckets; controls: later 5-min
  buckets), then sessions 1..10 on daily bars. The fill bar's own high is never credited.
  CONTROL = every 5-min bucket close with m >= 630 on the EP days of the campaigns that FIRED under that rule
  (H2's fires_by_c precedent), excluding the fire's own bucket. The same-day control also neutralises H2's
  session-range artefact by design (same stock, same day, same yardstick).
  GAP = fire +2-first % minus control +2-first % (pooled rows, the H2 convention) = "pts".
  Beside (not in the verdict): the per-campaign PAIRED gap (fire hit minus that campaign's own control rate), the
  -1-first gap, the opt bound, the fillable entry (bstop: fill x (1 + 5 bps); close: next bucket open + 5 bps;
  5 bps on every exit), week-block permutation p (perm_group, labels shuffled within the EP date's ISO week, 2000
  draws, seed 327; perm_paired for the paired gap), full-bar days only, without TEAM, in-sample vs held-out week.

THE PASS BAR, mechanised (ERA A = all 261-campaign ERA A; rule bstop; recorded entry; pess; original barriers):
  L1 gap >= +5 pts · L2 n readable fires >= 100 on >= 60 names · L3 gap after dropping the two fire names with the
  most +2 hits (and their controls) >= +5 pts (the H2 report's own drop-2 rule) · L4 gap > 0 on ERA A ex-May
  (alert month June-August) · L5 ERA B gap > 0 (ERA B with < 8 readable fires = "can't tell", the 09-27 MIN_HELDOUT).
  VERDICT: L2 fails -> NOT_TESTABLE (the trigger cannot reach the bar's power on this population; direction
  printed — a rarely-firing trigger is not a FAIL). Else any of L1/L3/L4 fails -> FAIL. Else L5 negative -> FAIL;
  L5 can't tell -> NOT_TESTABLE (ERA B leg). Else PASS. ONE primary draw; everything else is shown, not counted.
  TEAM reproduction (fill within 11:50-12:20 ET) is a VALIDITY check on the mechanics, reported first.

OTHER MEASURES (same row): same-day stop rate (stopped on day 0 at the H7 stop) fires vs controls (control stop =
  entry - 0.5 ADR$, the floor); the TAIL = share of fires ending >= 3R through the lane's own compute_settlement
  (reentry.settle_attempt), trail arm (close below max(SMA10, SMA20)), gap-through stops charged at the open, mark at
  the 09-25 horizon when open — vs the same for controls; mean R, drop-best-two R, worst loss; winner capture = of
  the rerun's 7 big-winner EPs (summary.json, never hand-listed) and his 4 labelled EPs in the 277
  (shared.operator_labelled_eps), how many are in the restricted population, fire, and end >= 3R. Descriptive: the
  lane's FIRST fire on the same campaigns (reentry_rows attempt 1, own stop, trail).

EXPECTED BEFORE RUNNING (stated so a surprise is visible): most EP days break the ORB low (> 70%); the trigger fires
  on roughly 80-130 ERA A campaigns (n close to the 100 floor); the 0.5 floor binds on > 90% of fires; the gap vs the
  same-day control is small (|gap| < 5 pts) because a 620 turn inside one afternoon carries little information
  beyond the day's own path; ERA B has fewer than 8 fires (can't tell); TEAM itself is a large winner.

ANCHORS (phase `anchor`, 0 drift required before `run`):
  (a) TEAM 08-07 merged day-0: 78 five-min buckets; MACD/signal at 11:10/11:15/11:40/12:05 = -1.86/-1.28,
      -1.72/-1.37, -1.54/-1.58, -0.89/-1.27 (hyp_team_handwalk.txt, 620_chart.md); a qualified cross at 11:40 close
      143.68.
  (b) every Saturday key's merged 1-min RTH count == n_rth in sat_day0_pull_status.tsv (50 of 50).
  (c) this probe's +2/-1 walker reproduces every hyp_rows_h2.tsv fire row (barrier orig, bound pess, entry rec).
  (d) settlement on a day-0 fire: TEAM 11:40 cross close 143.68, stop 141.51 -> trail +21.15R, fillable +20.59R
      (the 09-27 hand-walk).

Usage:  python3 h7_run.py gate | anchor | run | report      (run ONCE; the report reads the row files)
Outputs: h7_gate_out.txt, h7_anchor_out.txt, h7_campaigns.tsv, h7_fires.tsv, h7_controls.tsv, h7_report.txt,
         h7_summary.json
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

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
for p in (REPO, REPO / "scripts" / "probes", REPO / "scripts" / "probes" / "_327_block5", HERE):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import hyptests as H                                   # noqa: E402  loaders, settle_first, slip_r, fill_entry
import rerun                                           # noqa: E402
import reentry                                         # noqa: E402
import p2_probe                                        # noqa: E402  first_passage / at_checkpoint (the H2 instrument)
from hyptests_report import perm_group, perm_paired    # noqa: E402  the program's week-block permutations
from agents.market_intelligence.delayed_entry_shadow import (   # noqa: E402  real code
    _trading_days, macd_620, qualified_620_crosses, to_rth_5min, BASING_BARS)

_ET = ZoneInfo("America/New_York")
HORIZON = H.HORIZON                 # 2026-09-25 — the program's horizon, daily.tsv's last session
ERA_SPLIT = H.ERA_SPLIT
DISC_END = H.DISC_END
BPS = H.BPS
TAIL_R = 3.0
T_MIN = 630                         # 10:30 ET bucket label
REACH_K = 0.5
FLOOR_K = 0.5
MIN_BARS, FULL_BARS = 100, 300
MIN_HELDOUT = 8
K_CHECK = 10
TEAM = ("TEAM", date(2026, 8, 7))
TEAM_WINDOW = (11 * 60 + 50, 12 * 60 + 20)      # 12:05 +- 15 min
RULES = ("bstop", "close")
STOP, TARGET, OPEN, ABSTAIN = p2_probe.STOP, p2_probe.TARGET, p2_probe.OPEN, p2_probe.ABSTAIN


def hhmm(m):
    return "—" if m is None else f"{int(m) // 60:02d}:{int(m) % 60:02d}"


def fm(x, f="{:+.2f}"):
    return "—" if x is None else f.format(x)


def mean(v):
    return statistics.mean(v) if v else None


def sessions_after(d, n=20):
    return _trading_days(d + timedelta(days=1), HORIZON)[:n]


# ── loaders ───────────────────────────────────────────────────────────────────────────────────────────

def load_sat():
    out = defaultdict(list)
    with gzip.open(HERE / "sat_day0_minutes.tsv.gz", "rt") as fh:
        rd = csv.reader(fh, delimiter="|")
        hdr = next(rd)
        for r in rd:
            x = dict(zip(hdr, r))
            t = int(float(x["t_ms"]))
            et = datetime.fromtimestamp(t / 1000, tz=timezone.utc).astimezone(_ET)
            m = et.hour * 60 + et.minute
            if not (570 <= m < 960) or et.date().isoformat() != x["d"]:
                continue
            out[(x["ticker"], date.fromisoformat(x["d"]))].append(
                {"t": t, "m": m, "o": float(x["o"]), "h": float(x["h"]), "l": float(x["l"]), "c": float(x["c"])})
    for v in out.values():
        v.sort(key=lambda b: b["t"])
    return out


def load_all():
    D = H.load_everything()            # alerts, camps, fires, daily, raw (>=100-bar sessions), dropped, min5, runners, labelled
    sat = load_sat()
    status = {(r["ticker"], date.fromisoformat(r["d"])): int(r["n_rth"]) for r in rerun.read_tsv(HERE / "sat_day0_pull_status.tsv")}
    day0 = {}
    for a in D["alerts"]:
        k = (a["ticker"], a["ep_date"])
        n_old = len(D["raw"][k]) if k in D["raw"] else D["dropped"].get(k, 0)
        if k in sat:
            b1, src = sat[k], "sat_polygon"
        else:
            b1, src = (D["raw"].get(k) or []), "minute_tsv"
        n = len(b1)
        cls = "dark" if n < MIN_BARS else ("thin" if n < FULL_BARS else "full")
        cls_old = "none" if n_old == 0 else ("one_bar" if n_old < 100 else ("partial" if n_old < FULL_BARS else "full"))
        day0[k] = {"b1": b1 if cls != "dark" else [], "src": src, "n1": n, "cls": cls, "cls_old": cls_old, "n_old": n_old}
    D["sat"], D["sat_status"], D["day0"] = sat, status, day0
    return D


def campaign_ctx(D, a):
    k = (a["ticker"], a["ep_date"])
    c = D["camps"][k]
    adr = c["adr_dollar"]
    epb = D["daily"].get(a["ticker"], {}).get(a["ep_date"])
    if not epb or epb["close"] is None or adr is None or adr <= 0:
        return None, adr, epb
    f0 = {"ticker": a["ticker"], "ep_date": a["ep_date"], "ep_low": epb["low_price"], "ep_close": epb["close"],
          "ep_high": epb["high_price"], "adr_dollar": adr}
    return reentry.make_ctx(f0, D["daily"]), adr, epb


# ── the +2/-1 walker (the H2 instrument, identical to hyptests_run.h2_rows.walk) ───────────────────────

def walk(entry, y, d0_bars, after_sessions, ctx, bound):
    bars = list(d0_bars) + [((ctx["bars"][d]["high_price"], ctx["bars"][d]["low_price"])
                             if d in ctx["bars"] and ctx["bars"][d]["high_price"] is not None else None) for d in after_sessions]
    ev, idx = p2_probe.first_passage(bars, entry, entry - y, entry + 2 * y, bound)
    return p2_probe.at_checkpoint(ev, idx, K_CHECK, len(d0_bars))


# ── the trigger ───────────────────────────────────────────────────────────────────────────────────────

def find_trigger(c, rule):
    """c: day-0 campaign dict. Returns (fire or None, Counter of rejections)."""
    b1, b5, adr = c["b1"], c["b5"], c["adr"]
    rej = Counter()
    live_until = -1
    for i, close in qualified_620_crosses(b5, adr, 0):
        b = b5[i]
        m = b["m"]
        rej["qualified_crosses"] += 1
        if m < T_MIN:
            rej["r1_before_1030"] += 1
            continue
        if c["break_m"] is None or c["break_m"] > m + 4:
            rej["r2_no_shakeout_yet"] += 1
            continue
        d_open = abs(close - c["ep_open"]) / adr if c["ep_open"] is not None else None
        d_orb = abs(close - c["orb_low"]) / adr
        near_open = d_open is not None and d_open <= REACH_K + 1e-12
        near_orb = d_orb <= REACH_K + 1e-12
        if not (near_open or near_orb):
            rej["r3_out_of_reach"] += 1
            continue
        if m + 5 <= live_until:
            rej["skipped_while_armed"] += 1
            continue
        basing_low = min(x["l"] for x in b5[i - BASING_BARS:i + 1])
        reach = "both" if (near_open and near_orb) else ("open" if near_open else "orb_low")
        base = {"cross_m": m, "cross_close": close, "cross_high": b["h"], "basing_low": basing_low, "reach": reach,
                "d_open_adr": d_open, "d_orb_adr": d_orb, "cross_idx": i}
        if rule == "close":
            entry = close
            post = [x for x in b5 if x["m"] > m]
            return {**base, "entry": entry, "fm": m, "fill_m": m, "fire_bucket": m, "post": post}, rej
        level = b["h"]
        status, t_end, fill, fill_m = "expired", None, None, None
        for x in b1:
            if x["m"] < m + 5:
                continue
            if x["l"] <= basing_low:
                status, t_end = "cancel", x["m"]
                break
            if x["h"] >= level:
                status, fill, fill_m = "fill", max(level, x["o"]), x["m"]
                break
        if status == "fill":
            fb = fill_m - ((fill_m - 570) % 5)
            post = [{"m": x["m"], "h": x["h"], "l": x["l"]} for x in b1 if fill_m < x["m"] < fb + 5] + \
                   [x for x in b5 if x["m"] >= fb + 5]
            return {**base, "entry": fill, "fm": fill_m, "fill_m": fill_m, "fire_bucket": fb, "post": post,
                    "level": level}, rej
        if status == "cancel":
            rej["arm_cancelled_base_broke"] += 1
            live_until = t_end
            continue
        rej["arm_expired_no_fill"] += 1
        return None, rej
    return None, rej


def build_day0(D, a):
    k = (a["ticker"], a["ep_date"])
    d0 = D["day0"][k]
    ctx, adr, epb = campaign_ctx(D, a)
    c = {"ticker": a["ticker"], "ep_date": a["ep_date"], "era": a["era"], "split": H.split_of(a["ep_date"], a["era"]),
         "week": H.week_of(a["ep_date"]), "month": a["ep_date"].month, "cls": d0["cls"], "cls_old": d0["cls_old"],
         "src": d0["src"], "n1": d0["n1"], "adr": adr, "ctx": ctx, "b1": d0["b1"],
         "ep_open": (epb or {}).get("open_price"), "status": None}
    if d0["cls"] == "dark":
        c["status"] = "dark_day0"
        return c
    if ctx is None:
        c["status"] = "no_adr_or_ep_bar"
        return c
    b1 = d0["b1"]
    c["b5"] = to_rth_5min(b1, a["ep_date"])
    c["first_m"] = b1[0]["m"]
    c["orb_low"] = b1[0]["l"]
    c["orb_high"] = b1[0]["h"]
    brk = next((x for x in b1[1:] if x["l"] < c["orb_low"]), None)
    c["break_m"] = brk["m"] if brk else None
    c["day0_low"] = min(x["l"] for x in b1)
    c["status"] = "in_pop" if brk else "no_shakeout"
    return c


# ── phases ────────────────────────────────────────────────────────────────────────────────────────────

def phase_gate():
    D = load_all()
    L, ok = [], True

    def chk(cond, text):
        nonlocal ok
        ok &= bool(cond)
        L.append(("ok  " if cond else "MISMATCH ") + text)

    al = D["alerts"]
    A = [a for a in al if a["era"] == "A"]
    B = [a for a in al if a["era"] == "B"]
    chk(len(al) == 277 and len(A) == 261 and len(B) == 16, f"alerts: {len(al)} campaigns, ERA A {len(A)}, ERA B {len(B)}")
    chk(all((a["ep_date"] < ERA_SPLIT) == (a["era"] == "A") for a in al), "era label == alert_date < 2026-08-22")
    co = Counter((a["era"], D["day0"][(a["ticker"], a["ep_date"])]["cls_old"]) for a in al)
    chk(co[("A", "full")] == 212, f"minute.tsv.gz ALONE, EP-day classes (>=300 full): ERA A {dict((k[1], v) for k, v in co.items() if k[0] == 'A')}; "
                                   f"ERA B {dict((k[1], v) for k, v in co.items() if k[0] == 'B')} (hypotheses doc: 212 full / 11 partial / 35 one-bar / 3 none; ERA B 15 of 16)")
    chk(co[("B", "full")] == 15, "ERA B full on minute.tsv.gz alone == 15 of 16")
    sk = set(D["sat"])
    keys = {(a["ticker"], a["ep_date"]) for a in al}
    nonfull_old = {k for k in keys if D["day0"][k]["cls_old"] != "full"}
    chk(sk <= keys and sk == nonfull_old, f"sat_day0_minutes keys ({len(sk)}) == the 277's non-full EP days on minute.tsv.gz ({len(nonfull_old)})")
    cn = Counter((a["era"], D["day0"][(a["ticker"], a["ep_date"])]["cls"]) for a in al)
    L.append(f"    MERGED EP-day classes: ERA A {dict((k[1], v) for k, v in cn.items() if k[0] == 'A')}; ERA B {dict((k[1], v) for k, v in cn.items() if k[0] == 'B')}")
    dark = [f"{k[0]} {k[1]} ({D['day0'][k]['n1']} bars)" for k in sorted(keys) if D["day0"][k]["cls"] == "dark"]
    L.append(f"    DARK EP days (< {MIN_BARS} RTH 1-min bars after the merge; counted, never imputed): {len(dark)} {dark}")
    for tk in (TEAM, ("MRNA", date(2026, 8, 19)), ("PLTR", date(2026, 8, 4)), ("HTFL", date(2026, 8, 14))):
        chk(tk in keys, f"named campaign present: {tk[0]} {tk[1]}")
    chk(len(D["runners"]) == 7, f"rerun's big-winner EPs (summary.json): {sorted(D['runners'])}")
    L.append(f"    his labelled EPs in the 277: {sorted(D['labelled'])}")
    txt = "\n".join(L) + f"\n\nGATE {'PASSED' if ok else 'FAILED — HALT'}\n"
    (HERE / "h7_gate_out.txt").write_text(txt)
    print(txt)
    if not ok:
        sys.exit(1)


def phase_anchor():
    D = load_all()
    L, ok = [], True

    def chk(cond, text):
        nonlocal ok
        ok &= bool(cond)
        L.append(("ok  " if cond else "MISMATCH ") + text)

    # (a) TEAM day-0 MACD values and the qualified cross
    a = next(x for x in D["alerts"] if (x["ticker"], x["ep_date"]) == TEAM)
    c = build_day0(D, a)
    b5 = c["b5"]
    macd, sig = macd_620([b["c"] for b in b5])
    want = {670: (-1.86, -1.28), 675: (-1.72, -1.37), 700: (-1.54, -1.58), 725: (-0.89, -1.27)}
    got = {}
    for m_, (wm, ws) in want.items():
        i = next(j for j, b in enumerate(b5) if b["m"] == m_)
        got[m_] = (round(macd[i], 2), round(sig[i], 2))
    chk(len(b5) == 78, f"(a) TEAM 08-07 merged day-0 buckets = {len(b5)} (want 78; src {c['src']})")
    chk(all(got[m_] == want[m_] for m_ in want), f"(a) TEAM MACD/signal at 11:10/11:15/11:40/12:05: {[(hhmm(m_), got[m_]) for m_ in want]}")
    q = [(hhmm(b5[i]["m"]), round(cl, 2)) for i, cl in qualified_620_crosses(b5, c["adr"], 0)]
    chk(("11:40", 143.68) in q, f"(a) TEAM qualified 620 crosses on day 0: {q}")
    # (b) Saturday keys
    mism = [(k, len(D["sat"][k]), D["sat_status"].get(k)) for k in D["sat"] if len(D["sat"][k]) != D["sat_status"].get(k)]
    chk(not mism and len(D["sat"]) == 50, f"(b) Saturday keys' merged 1-min RTH counts == pull status n_rth: {len(D['sat']) - len(mism)} of {len(D['sat'])} {mism[:5]}")
    # (c) the +2/-1 walker on hyp_rows_h2.tsv fire rows (orig / pess / rec)
    ref = {}
    for r in rerun.read_tsv(HERE / "hyp_rows_h2.tsv"):
        if r["is_fire"] == "1" and r["barrier"] == "orig" and r["bound"] == "pess" and r["entry_kind"] == "rec":
            ref[(r["ticker"], r["ep_date"], r["pattern"])] = r["outcome"]
    n_cmp = n_ok = 0
    bad = []
    for f in D["fires"]:
        key = (f["ticker"], f["ep_date"].isoformat(), f["rung"])
        if key not in ref:
            continue
        ctx = reentry.make_ctx(f, D["daily"])
        y = f["adr_dollar"]
        after = sessions_after(f["fire_date"])
        b5f = D["min5"].get((f["ticker"], f["fire_date"])) or []
        fb = ctx["bars"].get(f["fire_date"]) or {}
        fmn = f["fire_minute"]
        d0_cache = (f["day0_resolved"], f["day0_post_low"], f["day0_post_high"]) if f["source"] == "lane_recorded" else None
        if fmn is None:
            d0 = [(fb["high_price"], fb["low_price"])] if fb.get("high_price") is not None else None
        elif b5f:
            d0 = [(x["h"], x["l"]) for x in b5f if x["m"] > fmn]
        elif d0_cache is not None and reentry.day0_pseudo_bars(*d0_cache) is not None:
            d0 = [(x["h"], x["l"]) for x in reentry.day0_pseudo_bars(*d0_cache)]
        else:
            d0 = None
        if d0 is None:
            o = ABSTAIN if (fb.get("low_price") is not None and fb["low_price"] <= f["entry"] - y) else walk(f["entry"], y, [], after, ctx, "pess")
        else:
            o = walk(f["entry"], y, d0, after, ctx, "pess")
        n_cmp += 1
        if o == ref[key]:
            n_ok += 1
        else:
            bad.append((key, o, ref[key]))
    chk(n_cmp == len(ref) and n_ok == n_cmp, f"(c) +2/-1 walker reproduces hyp_rows_h2.tsv fire rows (orig/pess/rec): {n_ok} of {n_cmp} (ref rows {len(ref)}) {bad[:5]}")
    # (d) settlement on a day-0 fire: TEAM 11:40 cross close, stop 141.51
    ctx = c["ctx"]
    fake = {"ticker": "TEAM", "ep_date": TEAM[1], "fire_date": TEAM[1], "fire_minute": 700, "entry": 143.68, "stop": 141.51,
            "source": "replay", "adr_dollar": c["adr"]}
    sb = H.settle_both(ctx, {(TEAM[0], TEAM[1]): b5}, fake, lambda e: 141.51, None)
    rt = sb["rec"]["trail"][1] if sb["rec"].get("status") in ("settled", "marked") else None
    ft = sb["fill"]["trail"][1] if sb["fill"].get("status") in ("settled", "marked") else None
    chk(rt is not None and abs(rt - 21.15) < 0.006 and ft is not None and abs(ft - 20.59) < 0.006,
        f"(d) TEAM day-0 11:40 cross 143.68 / stop 141.51 through compute_settlement: trail {fm(rt)}R (want +21.15), fillable {fm(ft)}R (want +20.59)")
    txt = "\n".join(L) + f"\n\nANCHORS {'PASSED (0 drift)' if ok else 'FAILED — HALT'}\n"
    (HERE / "h7_anchor_out.txt").write_text(txt)
    print(txt)
    if not ok:
        sys.exit(1)


def settle(ctx, post, entry, stop, fm_, ep, fill=False):
    """Recorded settlement (or fillable with 5 bps on exit) through the lane's compute_settlement; returns dict."""
    f = {"fire_minute": fm_}
    r = H.settle_first(ctx, {(ctx["tkr"], ep): post}, f, entry, stop, fm_, ep)
    if r.get("status") not in ("settled", "marked"):
        return {"status": r.get("status"), "trail": None, "none": None, "trail_oc": None, "same_day_stop": None}
    out = {"status": r["status"], "mfe": r.get("mfe")}
    for arm in ("trail", "none"):
        oc, rr, g = r[arm]
        if fill:
            rr = H.slip_r(entry, stop, rr, g)
        out[arm] = rr
        out[arm + "_oc"] = oc
    out["same_day_stop"] = int(r["none"][0] == "stop" and r.get("stop_idx") == 0)
    return out


def phase_run():
    D = load_all()
    camp_rows, fire_rows, ctl_rows = [], [], []
    a1 = H.load_reentry_attempt1()
    fires_by_c = defaultdict(list)
    for f in D["fires"]:
        fires_by_c[(f["ticker"], f["ep_date"])].append(f)
    for a in D["alerts"]:
        c = build_day0(D, a)
        k = (a["ticker"], a["ep_date"])
        row = {"ticker": a["ticker"], "ep_date": a["ep_date"].isoformat(), "era": a["era"], "split": c["split"],
               "month": c["month"], "week": c["week"], "cls_minute_tsv": c["cls_old"], "cls_merged": c["cls"], "src": c["src"],
               "n1": c["n1"], "status": c["status"], "adr": c["adr"], "ep_open": c["ep_open"],
               "is_runner": int((a["ticker"], a["ep_date"].isoformat()) in D["runners"]),
               "is_labelled": int((a["ticker"], a["ep_date"].isoformat()) in D["labelled"])}
        # the lane's first fire (descriptive)
        lf = sorted(fires_by_c.get(k, []), key=lambda f: (f["fire_date"], f["fire_minute"] if f["fire_minute"] is not None else -1))
        if lf:
            ref = a1.get((lf[0]["ticker"], lf[0]["ep_date"].isoformat(), lf[0]["rung"], "incumbent", "trail"))
            row["lane_first_trail_r"] = ref["r_gap"] if ref and ref["status"] in ("settled", "marked") else None
            row["lane_first_rung"], row["lane_first_date"] = lf[0]["rung"], lf[0]["fire_date"].isoformat()
        if c["status"] in ("dark_day0", "no_adr_or_ep_bar"):
            camp_rows.append(row)
            continue
        row.update({"first_m": hhmm(c["first_m"]), "orb_low": c["orb_low"], "break_m": hhmm(c["break_m"]),
                    "first_bar_late": int(c["first_m"] > 571)})
        ctx, adr, ep = c["ctx"], c["adr"], a["ep_date"]
        after = sessions_after(ep)
        fire_bucket = {}
        if c["status"] == "in_pop":
            for rule in RULES:
                fr, rej = find_trigger(c, rule)
                row[f"{rule}_rejections"] = ";".join(f"{kk}={vv}" for kk, vv in sorted(rej.items()))
                if fr is None:
                    row[f"{rule}_status"] = "no_fire"
                    continue
                row[f"{rule}_status"] = "fired"
                fire_bucket[rule] = fr["fire_bucket"]
                entry = fr["entry"]
                stop = min(fr["basing_low"], entry - FLOOR_K * adr)
                d0 = [(x["h"], x["l"]) for x in fr["post"]]
                o = {bnd: walk(entry, adr, d0, after, ctx, bnd) for bnd in ("pess", "opt")}
                rec = settle(ctx, fr["post"], entry, stop, fr["fm"], ep)
                unf = settle(ctx, fr["post"], entry, fr["basing_low"], fr["fm"], ep) if fr["basing_low"] < entry else {"trail": None, "same_day_stop": None, "status": "killed"}
                # fillable
                if rule == "bstop":
                    fe, fpost, ffm, fdate, fd0, fafter = entry * (1 + BPS), fr["post"], fr["fm"], ep, d0, after
                else:
                    fe_ = H.fill_entry({"fire_minute": fr["fm"], "fire_date": ep, "entry": entry}, {(a["ticker"], ep): c["b5"]}, ctx)
                    if fe_ is None:
                        fe = None
                    elif fe_["kind"] == "next_bucket":
                        fe, fpost, ffm, fdate = fe_["entry"], fe_["post5"], fe_["fm"], ep
                        fd0, fafter = [(x["h"], x["l"]) for x in fpost], after
                    else:
                        fe, fpost, ffm, fdate = fe_["entry"], None, None, fe_["fire_date"]
                        nb = ctx["bars"][fdate]
                        fd0, fafter = [(nb["high_price"], nb["low_price"])], sessions_after(fdate)
                if fe is not None:
                    fstop = min(fr["basing_low"], fe - FLOOR_K * adr)
                    fo = walk(fe, adr, fd0, fafter, ctx, "pess")
                    if fpost is not None:
                        fset = settle(ctx, fpost, fe, fstop, ffm, fdate, fill=True)
                    else:
                        r_ = H.settle_first(ctx, {}, {}, fe, fstop, None, fdate)
                        fset = {"trail": H.slip_r(fe, fstop, r_["trail"][1], r_["trail"][2]) if r_.get("status") in ("settled", "marked") else None}
                else:
                    fo, fset, fstop = None, {"trail": None}, None
                fire_rows.append({
                    "rule": rule, "ticker": a["ticker"], "ep_date": ep.isoformat(), "era": a["era"], "split": c["split"],
                    "month": c["month"], "week": c["week"], "cls": c["cls"], "src": c["src"],
                    "is_runner": row["is_runner"], "is_labelled": row["is_labelled"],
                    "cross_m": hhmm(fr["cross_m"]), "fill_m": hhmm(fr["fill_m"]), "fill_min": fr["fill_m"], "reach": fr["reach"],
                    "d_open_adr": round(fr["d_open_adr"], 3) if fr["d_open_adr"] is not None else None,
                    "d_orb_adr": round(fr["d_orb_adr"], 3), "entry": round(entry, 4), "basing_low": fr["basing_low"],
                    "stop": round(stop, 4), "stop_w_adr": round((entry - stop) / adr, 3), "floor_binds": int(stop < fr["basing_low"] - 1e-12),
                    "basing_w_adr": round((entry - fr["basing_low"]) / adr, 3), "adr": adr,
                    "edge_pess": o["pess"], "edge_opt": o["opt"], "edge_fill_pess": fo,
                    "status": rec["status"], "trail_r": rec.get("trail"), "none_r": rec.get("none"), "trail_oc": rec.get("trail_oc"),
                    "same_day_stop": rec.get("same_day_stop"), "mfe_r": rec.get("mfe"),
                    "fill_trail_r": fset.get("trail"), "unfloored_trail_r": unf.get("trail"), "unfloored_same_day_stop": unf.get("same_day_stop"),
                    "lane_first_trail_r": row.get("lane_first_trail_r")})
        # controls: every 5-min close m >= 10:30 on this (readable, shakeout) EP day
        if c["status"] == "in_pop":
            b5 = c["b5"]
            for j, y in enumerate(b5):
                if y["m"] < T_MIN:
                    continue
                post = b5[j + 1:]
                d0 = [(x["h"], x["l"]) for x in post]
                entry = y["c"]
                o = {bnd: walk(entry, adr, d0, after, ctx, bnd) for bnd in ("pess", "opt")}
                st = settle(ctx, post, entry, entry - FLOOR_K * adr, y["m"], ep)
                ctl_rows.append({"ticker": a["ticker"], "ep_date": ep.isoformat(), "era": a["era"], "split": c["split"],
                                 "month": c["month"], "week": c["week"], "cls": c["cls"], "m": y["m"],
                                 "pre_break": int(c["break_m"] is not None and y["m"] + 4 < c["break_m"]),
                                 "is_fire_bucket_bstop": int(fire_bucket.get("bstop") == y["m"]),
                                 "is_fire_bucket_close": int(fire_bucket.get("close") == y["m"]),
                                 "edge_pess": o["pess"], "edge_opt": o["opt"], "status": st["status"],
                                 "trail_r": st.get("trail"), "none_r": st.get("none"), "same_day_stop": st.get("same_day_stop")})
        camp_rows.append(row)

    def w(path, rows):
        cols = []
        for r in rows:
            for k_ in r:
                if k_ not in cols:
                    cols.append(k_)
        with open(HERE / path, "w") as fh:
            fh.write("|".join(cols) + "\n")
            for r in rows:
                fh.write("|".join("" if r.get(k_) is None else str(r.get(k_)) for k_ in cols) + "\n")
        print(f"wrote {path}: {len(rows)} rows")

    w("h7_campaigns.tsv", camp_rows)
    w("h7_fires.tsv", fire_rows)
    w("h7_controls.tsv", ctl_rows)


# ── report ────────────────────────────────────────────────────────────────────────────────────────────

def _f(v):
    return rerun._f(v)


def edge_stats(fires, ctls, field="edge_pess", ctl_field=None, want_p=False):
    """Pooled +2-first gap (pts), -1-first gap, drop-2 gap, week-block p, paired per-campaign gap + p."""
    ctl_field = ctl_field or ("edge_pess" if field == "edge_fill_pess" else field)
    fr = [r for r in fires if r[field] not in ("abstain", "", None)]
    keys = {(r["ticker"], r["ep_date"]) for r in fr}
    co = [r for r in ctls if (r["ticker"], r["ep_date"]) in keys and r[ctl_field] not in ("abstain", "", None)]
    out = {"n_fire": len(fr), "names": len({r["ticker"] for r in fr}), "n_ctl": len(co),
           "fire_abstain": sum(1 for r in fires if r[field] == "abstain")}
    if not fr or not co:
        return out
    pf = 100 * sum(r[field] == TARGET for r in fr) / len(fr)
    pc = 100 * sum(r[ctl_field] == TARGET for r in co) / len(co)
    sf = 100 * sum(r[field] == STOP for r in fr) / len(fr)
    sc = 100 * sum(r[ctl_field] == STOP for r in co) / len(co)
    out.update({"fire_plus2": pf, "ctl_plus2": pc, "gap": pf - pc, "fire_minus1": sf, "ctl_minus1": sc, "gap_minus1": sf - sc,
                "fire_open": sum(r[field] == OPEN for r in fr)})
    hits = Counter(r["ticker"] for r in fr if r[field] == TARGET)
    top = {t for t, _ in hits.most_common(2)}
    fr2 = [r for r in fr if r["ticker"] not in top]
    co2 = [r for r in co if r["ticker"] not in top]
    if fr2 and co2:
        out["gap_drop2"] = 100 * sum(r[field] == TARGET for r in fr2) / len(fr2) - 100 * sum(r[ctl_field] == TARGET for r in co2) / len(co2)
        out["drop2_names"] = sorted(top)
    allr = [(1.0 if r[field] == TARGET else 0.0, True, r["week"]) for r in fr] + [(1.0 if r[ctl_field] == TARGET else 0.0, False, r["week"]) for r in co]
    out["p"] = perm_group([x[0] for x in allr], [x[1] for x in allr], [x[2] for x in allr]) if (want_p and len(fr) >= 2) else None
    # paired per campaign
    cr = defaultdict(list)
    for r in co:
        cr[(r["ticker"], r["ep_date"])].append(1.0 if r[ctl_field] == TARGET else 0.0)
    diffs, weeks = [], []
    for r in fr:
        k = (r["ticker"], r["ep_date"])
        if cr.get(k):
            diffs.append(100 * ((1.0 if r[field] == TARGET else 0.0) - mean(cr[k])))
            weeks.append(r["week"])
    out["paired_gap"] = mean(diffs)
    out["paired_n"] = len(diffs)
    out["paired_p"] = perm_paired(diffs, weeks) if len(diffs) >= 2 else None
    return out


def tail_stats(fires, ctls, rfield="trail_r"):
    fr = [r for r in fires if _f(r.get(rfield)) is not None]
    keys = {(r["ticker"], r["ep_date"]) for r in fires}
    co = [r for r in ctls if (r["ticker"], r["ep_date"]) in keys and _f(r.get("trail_r")) is not None]
    out = {"n": len(fr)}
    if not fr:
        return out
    rs = [_f(r[rfield]) for r in fr]
    by = defaultdict(float)
    for r in fr:
        by[r["ticker"]] += _f(r[rfield])
    top = sorted(by.items(), key=lambda kv: -kv[1])[:2]
    out.update({"mean_r": mean(rs), "sum_r": sum(rs), "sum_r_drop2": sum(rs) - sum(v for _, v in top),
                "drop2": [f"{t} {v:+.1f}" for t, v in top], "tail_n": sum(x >= TAIL_R - 1e-9 for x in rs),
                "tail_share": 100 * sum(x >= TAIL_R - 1e-9 for x in rs) / len(rs), "worst": min(rs),
                "tail_names": sorted(f"{r['ticker']} {_f(r[rfield]):+.1f}" for r in fr if _f(r[rfield]) >= TAIL_R - 1e-9)})
    sd = [r for r in fires if r.get("same_day_stop") not in ("", None)]
    out["same_day_stop"] = 100 * sum(int(r["same_day_stop"]) for r in sd) / len(sd) if sd else None
    if co:
        crs = [_f(r["trail_r"]) for r in co]
        out.update({"ctl_n": len(co), "ctl_mean_r": mean(crs), "ctl_tail_share": 100 * sum(x >= TAIL_R - 1e-9 for x in crs) / len(crs)})
        sdc = [r for r in co if r.get("same_day_stop") not in ("", None)]
        out["ctl_same_day_stop"] = 100 * sum(int(r["same_day_stop"]) for r in sdc) / len(sdc) if sdc else None
    return out


def phase_report():
    camps = rerun.read_tsv(HERE / "h7_campaigns.tsv")
    fires_all = rerun.read_tsv(HERE / "h7_fires.tsv")
    ctls_all = rerun.read_tsv(HERE / "h7_controls.tsv")
    S, L = {}, []
    # ── population ──
    P = {}
    for era in ("A", "B"):
        cs = [c for c in camps if c["era"] == era]
        st = Counter(c["status"] for c in cs)
        P[era] = {"campaigns": len(cs), "cls_minute_tsv": dict(Counter(c["cls_minute_tsv"] for c in cs)),
                  "cls_merged": dict(Counter(c["cls_merged"] for c in cs)), "status": dict(st),
                  "dark": sorted(f"{c['ticker']} {c['ep_date']} ({c['n1']} bars)" for c in cs if c["status"] == "dark_day0"),
                  "first_bar_late": sorted(f"{c['ticker']} {c['ep_date']} {c['first_m']}" for c in cs if c.get("first_bar_late") == "1"),
                  "in_pop": st.get("in_pop", 0), "in_pop_names": len({c["ticker"] for c in cs if c["status"] == "in_pop"}),
                  "fires": {rule: sum(1 for c in cs if c.get(f"{rule}_status") == "fired") for rule in RULES}}
        rejs = {rule: Counter() for rule in RULES}
        for c in cs:
            for rule in RULES:
                for kv in (c.get(f"{rule}_rejections") or "").split(";"):
                    if "=" in kv:
                        kk, vv = kv.split("=")
                        rejs[rule][kk] += int(vv)
        P[era]["rejections"] = {r: dict(v) for r, v in rejs.items()}
        P[era]["no_fire_campaigns"] = {rule: sum(1 for c in cs if c.get(f"{rule}_status") == "no_fire") for rule in RULES}
    for grp, key in (("runners", "is_runner"), ("labelled", "is_labelled")):
        cs = [c for c in camps if c[key] == "1"]
        P[grp] = [f"{c['ticker']} {c['ep_date']} {c['status']} bstop={c.get('bstop_status') or '—'} close={c.get('close_status') or '—'}" for c in cs]
    S["population"] = P
    L.append("=" * 118 + "\nH7 — day-0 afternoon re-entry after the opening shakeout (TEAM 08-07). Pre-registration: h7_run.py docstring.\n" + "=" * 118)
    L.append("POPULATION")
    for era in ("A", "B"):
        p = P[era]
        L.append(f"  ERA {era}: {p['campaigns']} campaigns | minute.tsv.gz alone {p['cls_minute_tsv']} | merged {p['cls_merged']} | status {p['status']}")
        L.append(f"    dark {len(p['dark'])}: {p['dark']} | first bar after 09:31: {p['first_bar_late']}")
        L.append(f"    restricted population (shakeout below the first 1-min bar's low): {p['in_pop']} campaigns / {p['in_pop_names']} names | fired: {p['fires']} | no fire: {p['no_fire_campaigns']}")
        for rule in RULES:
            L.append(f"    {rule} rejections (summed over crosses): {p['rejections'][rule]}")
    L.append(f"  big-winner EPs (7): {P['runners']}")
    L.append(f"  his labelled EPs (4): {P['labelled']}")
    # ── TEAM ──
    tm = [r for r in fires_all if (r["ticker"], r["ep_date"]) == ("TEAM", "2026-08-07")]
    S["team"] = {r["rule"]: {k: r[k] for k in ("cross_m", "fill_m", "entry", "stop", "basing_low", "stop_w_adr", "trail_r", "none_r", "unfloored_trail_r", "edge_pess", "fill_min")} for r in tm}
    L.append("\nTEAM 08-07 (validity check: fill within 11:50-12:20 ET; his entry ~12:05 at $144.39, stop 141.51)")
    for r in tm:
        inwin = TEAM_WINDOW[0] <= int(r["fill_min"]) <= TEAM_WINDOW[1]
        S["team"][r["rule"]]["reproduced"] = inwin
        L.append(f"  {r['rule']:6s}: cross {r['cross_m']} -> entry {r['fill_m']} at {float(r['entry']):.2f} | stop {float(r['stop']):.2f} ({r['stop_w_adr']} ADR; basing low {float(r['basing_low']):.2f}) | "
                 f"+2/-1: {r['edge_pess']} | trail {fm(_f(r['trail_r']))}R none {fm(_f(r['none_r']))}R | unfloored-stop trail {fm(_f(r['unfloored_trail_r']))}R | REPRODUCED {inwin}")
    # ── results per rule ──
    groups = [("ERA A", lambda r: r["era"] == "A"), ("ERA A ex-May", lambda r: r["era"] == "A" and r["month"] != "5"),
              ("ERA A May", lambda r: r["era"] == "A" and r["month"] == "5"),
              ("ERA A in-sample <=08-14", lambda r: r["split"] == "DISC"), ("ERA A held-out week 08-15..21", lambda r: r["split"] == "HOA"),
              ("ERA A full-bar days only", lambda r: r["era"] == "A" and r["cls"] == "full"),
              ("ERA A without TEAM", lambda r: r["era"] == "A" and r["ticker"] != "TEAM"), ("ERA B", lambda r: r["era"] == "B")]
    S["results"] = {}
    for rule in RULES:
        fires = [r for r in fires_all if r["rule"] == rule]
        ctls = [r for r in ctls_all if r[f"is_fire_bucket_{rule}"] != "1"]
        S["results"][rule] = {}
        L.append("\n" + "-" * 118 + f"\nRULE {rule}{'  (PRIMARY)' if rule == 'bstop' else '  (sensitivity: the lane-convention cross-close entry)'}\n" + "-" * 118)
        for gname, g in groups:
            fg = [r for r in fires if g(r)]
            cg = [r for r in ctls if g(r)]
            res = {"edge": edge_stats(fg, cg, want_p=gname in ("ERA A", "ERA A ex-May")), "edge_opt": edge_stats(fg, cg, "edge_opt"), "edge_fill": edge_stats(fg, cg, "edge_fill_pess"),
                   "tail": tail_stats(fg, cg), "tail_fill": tail_stats(fg, cg, "fill_trail_r"), "tail_unfloored": tail_stats(fg, cg, "unfloored_trail_r"),
                   "floor_binds": (100 * sum(r["floor_binds"] == "1" for r in fg) / len(fg)) if fg else None,
                   "stop_w_adr_median": statistics.median([_f(r["stop_w_adr"]) for r in fg]) if fg else None,
                   "basing_w_adr_median": statistics.median([_f(r["basing_w_adr"]) for r in fg]) if fg else None,
                   "reach": dict(Counter(r["reach"] for r in fg)),
                   "fill_time": dict(Counter(("10:30-11:59" if int(r["fill_min"]) < 720 else ("12:00-13:59" if int(r["fill_min"]) < 840 else "14:00+")) for r in fg))}
            lane = [(_f(r["trail_r"]), _f(r["lane_first_trail_r"])) for r in fg if _f(r["trail_r"]) is not None and _f(r["lane_first_trail_r"]) is not None]
            res["vs_lane_first"] = {"n": len(lane), "h7_mean": mean([x for x, _ in lane]), "lane_mean": mean([y for _, y in lane]),
                                    "h7_tail": sum(x >= TAIL_R for x, _ in lane), "lane_tail": sum(y >= TAIL_R for _, y in lane)}
            S["results"][rule][gname] = res
            e, eo, ef, t, tf, tu = res["edge"], res["edge_opt"], res["edge_fill"], res["tail"], res["tail_fill"], res["tail_unfloored"]
            L.append(f"  {gname}")
            L.append(f"    edge (+2 ADR before -1 ADR by s10, pess): fires {e['n_fire']} ({e['names']} names; abstain {e['fire_abstain']}) vs controls {e['n_ctl']} | "
                     f"+2 first {fm(e.get('fire_plus2'), '{:.1f}')}% vs {fm(e.get('ctl_plus2'), '{:.1f}')}% -> GAP {fm(e.get('gap'), '{:+.1f}')} pts "
                     f"(drop-2 {fm(e.get('gap_drop2'), '{:+.1f}')} {e.get('drop2_names', '')}; week-block p {fm(e.get('p'), '{:.3f}')}) | "
                     f"-1 first {fm(e.get('fire_minus1'), '{:.1f}')}% vs {fm(e.get('ctl_minus1'), '{:.1f}')}% ({fm(e.get('gap_minus1'), '{:+.1f}')})")
            L.append(f"    beside: paired per-campaign gap {fm(e.get('paired_gap'), '{:+.1f}')} pts (n {e.get('paired_n')}, p {fm(e.get('paired_p'), '{:.3f}')}) | "
                     f"opt bound gap {fm(eo.get('gap'), '{:+.1f}')} | fillable gap {fm(ef.get('gap'), '{:+.1f}')} (n {ef.get('n_fire')})")
            L.append(f"    R at the H7 stop (trail arm, gap-charged): n {t.get('n')} mean {fm(t.get('mean_r'))}R sum {fm(t.get('sum_r'), '{:+.1f}')} drop-2 {fm(t.get('sum_r_drop2'), '{:+.1f}')} {t.get('drop2', '')} | "
                     f">=3R {t.get('tail_n')} = {fm(t.get('tail_share'), '{:.1f}')}% vs controls {fm(t.get('ctl_tail_share'), '{:.1f}')}% (ctl mean {fm(t.get('ctl_mean_r'))}R, n {t.get('ctl_n')}) | "
                     f"worst {fm(t.get('worst'))} | same-day stop {fm(t.get('same_day_stop'), '{:.1f}')}% vs ctl {fm(t.get('ctl_same_day_stop'), '{:.1f}')}%")
            L.append(f"      tail names: {t.get('tail_names')}")
            L.append(f"    fillable R mean {fm(tf.get('mean_r'))} (>=3R {fm(tf.get('tail_share'), '{:.1f}')}%) | unfloored basing-low stop: mean {fm(tu.get('mean_r'))}R, >=3R {fm(tu.get('tail_share'), '{:.1f}')}%, worst {fm(tu.get('worst'))} | "
                     f"floor binds {fm(res['floor_binds'], '{:.0f}')}% | median stop {fm(res['stop_w_adr_median'], '{:.2f}')} ADR (basing {fm(res['basing_w_adr_median'], '{:.2f}')}) | reach {res['reach']} | fills {res['fill_time']}")
            v = res["vs_lane_first"]
            L.append(f"    vs the lane's first fire on the same campaigns (descriptive): n {v['n']} H7 {fm(v['h7_mean'])}R vs lane {fm(v['lane_mean'])}R; >=3R {v['h7_tail']} vs {v['lane_tail']}")
        # winners
        wl = []
        for r in fires:
            if r["is_runner"] == "1" or r["is_labelled"] == "1":
                wl.append(f"{r['ticker']} {r['ep_date']} {'runner' if r['is_runner'] == '1' else 'labelled'} trail {fm(_f(r['trail_r']))}R edge {r['edge_pess']}")
        S["results"][rule]["winners_fired"] = wl
        L.append(f"  winner capture (fired): {wl}")
    # ── verdict (primary: bstop, ERA A, recorded, pess) ──
    A = S["results"]["bstop"]["ERA A"]["edge"]
    XM = S["results"]["bstop"]["ERA A ex-May"]["edge"]
    B = S["results"]["bstop"]["ERA B"]["edge"]
    legs = {"L1 gap >= +5": (A.get("gap") is not None and A["gap"] >= 5),
            "L2 n >= 100 on >= 60 names": (A["n_fire"] >= 100 and A["names"] >= 60),
            "L3 drop-best-two >= +5": (A.get("gap_drop2") is not None and A["gap_drop2"] >= 5),
            "L4 ex-May > 0": (XM.get("gap") is not None and XM["gap"] > 0)}
    b_leg = "can't tell" if B["n_fire"] < MIN_HELDOUT else ("+" if (B.get("gap") or 0) > 0 else "-")
    legs["L5 ERA B same sign"] = b_leg
    if not legs["L2 n >= 100 on >= 60 names"]:
        verdict = "NOT_TESTABLE"
    elif not (legs["L1 gap >= +5"] and legs["L3 drop-best-two >= +5"] and legs["L4 ex-May > 0"]):
        verdict = "FAIL"
    elif b_leg == "-":
        verdict = "FAIL"
    elif b_leg == "can't tell":
        verdict = "NOT_TESTABLE"
    else:
        verdict = "PASS"
    S["verdict"] = {"legs": legs, "verdict": verdict, "program_extras": {"week_block_p": A.get("p"), "fillable_gap": S["results"]["bstop"]["ERA A"]["edge_fill"].get("gap")}}
    L.append("\n" + "=" * 118 + f"\nVERDICT against the verbatim bar (rule bstop, ERA A, recorded entry, pess): {verdict}")
    for k, v in legs.items():
        L.append(f"  {k}: {v}")
    L.append(f"  program extras (not in the verbatim bar): week-block p {fm(A.get('p'), '{:.3f}')}; fillable gap {fm(S['verdict']['program_extras']['fillable_gap'], '{:+.1f}')} pts")
    txt = "\n".join(L) + "\n"
    (HERE / "h7_report.txt").write_text(txt)
    (HERE / "h7_summary.json").write_text(json.dumps(S, indent=1, default=str))
    print(txt)
    print("wrote h7_report.txt, h7_summary.json")


if __name__ == "__main__":
    ph = sys.argv[1]
    {"gate": phase_gate, "anchor": phase_anchor, "run": phase_run, "report": phase_report}[ph]()
