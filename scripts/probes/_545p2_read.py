#!/usr/bin/env python3
"""#545 Phase 2 — THE MISSED-EP TAIL READ. OFFLINE reader, $0. Evidence only (THE LINE).

Reads ONLY committed captures:
  scripts/probes/_545p2_out.txt              capture 1 (09-02): per-bucket ret_20d tail shares, gapped-at-open only
  scripts/ep_replay_data/_pull2_out.txt      09-01: closed magna53 trades (live+paper), 270 live alerts, daily OHLC
  scripts/ep_replay_data/_pull4_min.tsv.gz   09-01: alert-day RTH minute bars (for the leg print of a few campaigns)
  scripts/ep_replay_data/campaigns_era_c.tsv 09-02: every live alert walked through the CURRENT day-1 bracket
  scripts/probes/_ladder_missed.tsv          08-14: alert-level missed rows with their skip bucket (02-11 -> 08-14)
  scripts/probes/_545p2_capture2_out.psv     OPTIONAL capture 2 (see _545p2_capture2.sql) — era/security-type split,
                                             ret_5d for the censored August rows, alert-level rows to 09-01

What it computes that capture 1 cannot:
  A. the PASS BAR — the traded cohort's OWN share on the same daily-grain proxy ((close_d20-open_d0)/open_d0 >= 0.20),
     replicating missed_outcomes.py's LATERALs exactly (OFFSET 19 for d20, OFFSET 4 for d5), on the 26 closed live
     trades, the 26 closed paper trades and the 270 admitted alerts — and the conversion of that tail into realized R;
  B. the LIVE-BRACKET half for the alert-level buckets — campaigns_era_c.tsv joined on (ticker, alert_date) to each
     skipped alert's bucket, with the full status distribution (settled / no_entry / no_trade / abstain) and R;
  C. the leg print for the prompting case (HTFL) and the other stop_too_wide names — checkable by hand;
  D. with capture 2: the same per bucket x month x security-type, and ret_5d beside ret_20d.

Traps carried (from the brief): ret_* are FRACTIONS; max_high_* is MFE, never a return; ret_20d is right-censored
(August unreadable at 20d); scan-level buckets have no ORB bars -> daily grain only; buckets OVERLAP (never sum).
Doc: docs/analysis/545p2_missed_ep_tail_read_2026-09-02.md.   Run: python3 scripts/probes/_545p2_read.py
"""
from __future__ import annotations

import io
import statistics
import sys
from collections import Counter, defaultdict
from contextlib import redirect_stdout
from datetime import date, datetime, time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO))
import ep_replay  # noqa: E402  (the validated harness; `validate` must PASS before any number here is quoted)

HERE = REPO / "scripts/probes"
CAP1 = HERE / "_545p2_out.txt"
CAP2 = HERE / "_545p2_capture2_out.psv"
LADDER = HERE / "_ladder_missed.tsv"
CAMP = REPO / "scripts/ep_replay_data/campaigns_era_c.tsv"
OUT = HERE / "_545p2_read_out.txt"

TAIL = 0.20          # the pre-registered daily-grain tail bar: >= +20% at 20 sessions from the gap-day open
SECTYPE_FILTER_DATE = date(2026, 4, 20)   # commit 171b03d0 — ETF/warrant exclusion; rows before it are a different scan
# The 9 MAGNA53 stop_too_wide rejects, from scripts/probes/stop_too_wide_cohort.py (the only bucket ever read, 08-17)
STOP_TOO_WIDE = {("STRL", date(2026, 5, 5)), ("EVER", date(2026, 5, 5)), ("AIP", date(2026, 5, 13)),
                 ("GO", date(2026, 5, 14)), ("PONY", date(2026, 5, 26)), ("CORT", date(2026, 7, 30)),
                 ("AEVA", date(2026, 8, 6)), ("ATRO", date(2026, 8, 12)), ("HTFL", date(2026, 8, 14))}


# ── parsers ───────────────────────────────────────────────────────────────────────────────────
def _f(v):
    if v in (None, "", "\\N"):
        return None
    try:
        return float(v)
    except ValueError:
        return None


def parse_aligned(path: Path) -> dict[str, list[dict]]:
    """psql ALIGNED output with `\\echo ===NAME===` section markers (capture 1)."""
    out: dict[str, list[dict]] = {}
    cur, hdr = None, None
    for ln in path.read_text().splitlines():
        if ln.startswith("===") and ln.endswith("==="):
            cur, hdr = ln.strip("="), None
            out[cur] = []
            continue
        if cur is None or not ln.strip() or ln.startswith("(") or set(ln.strip()) <= set("-+"):
            continue
        cells = [c.strip() for c in ln.split("|")]
        if hdr is None:
            hdr = cells
            continue
        if len(cells) == len(hdr):
            out[cur].append(dict(zip(hdr, cells)))
    return out


def parse_psv(path: Path) -> dict[str, list[dict]]:
    """psql -A -F '|' output with `=== NAME ===` markers (capture 2, same shape as _pull2_out.txt)."""
    return ep_replay.read_sections(path)


def parse_tsv_pipe(path: Path, cols: list[str]) -> list[dict]:
    rows = []
    for ln in path.read_text().splitlines():
        p = ln.rstrip("\n").split("|")
        if len(p) == len(cols):
            rows.append(dict(zip(cols, p)))
    return rows


# ── the LIVE partial path ─────────────────────────────────────────────────────────────────────
# The harness books the day-3/day-5 LADDER partial (exit_logic.py:336) inside apply_daily_exit_step. Live
# stands that branch down while the intraday +2R trigger is on (live_tracker.py:1076,
# skip_partial_decision=bool(PROFIT_TRIGGER_R)); the +2R partial itself is already modelled in walk_campaign's
# daily loop (high >= target -> 1/3 at the target, breakeven). So the live path = the harness with the ladder
# partial disabled. A deviation-corrected VARIANT, not the validated harness — both paths are reported.
_orig_step = ep_replay.apply_daily_exit_step


def _step_no_ladder(state, bar, today, **kw):
    kw["skip_partial_decision"] = True
    return _orig_step(state, bar, today, **kw)


def walk_live_path(**kw) -> dict:
    ep_replay.apply_daily_exit_step = _step_no_ladder
    try:
        return ep_replay.walk_campaign(**kw)
    finally:
        ep_replay.apply_daily_exit_step = _orig_step


# ── the daily-grain proxy, replicating missed_outcomes.py:600-660 exactly ─────────────────────
def daily_proxy(daily: dict[str, dict[date, dict]], ticker: str, d0: date) -> dict:
    bars = daily.get(ticker, {})
    if d0 not in bars or bars[d0]["o"] is None:
        return {"open_d0": None, "close_d0": None, "ret_5d": None, "ret_20d": None, "max_high_20d": None,
                "open_gap": None, "gapped": None}
    o0, c0 = bars[d0]["o"], bars[d0]["c"]
    prior = [bars[d]["c"] for d in sorted(bars) if d < d0 and bars[d]["c"] is not None]
    gap = (o0 - prior[-1]) / prior[-1] if (prior and prior[-1] > 0) else None
    after = [bars[d] for d in sorted(bars) if d > d0 and bars[d]["c"] is not None]
    from_d0 = [bars[d] for d in sorted(bars) if d >= d0 and bars[d]["h"] is not None]
    c5 = after[4]["c"] if len(after) > 4 else None
    c20 = after[19]["c"] if len(after) > 19 else None
    mh20 = max(b["h"] for b in from_d0[:21]) if from_d0 else None
    return {"open_d0": o0, "close_d0": c0, "open_gap": gap, "gapped": (gap is not None and gap >= 0.09),
            "ret_5d": (c5 - o0) / o0 if (c5 is not None and o0 > 0) else None,
            "ret_20d": (c20 - o0) / o0 if (c20 is not None and o0 > 0) else None,
            "max_high_20d": (mh20 - o0) / o0 if (mh20 is not None and o0 > 0) else None}


def tail_stats(rows: list[dict], key: str = "ret_20d") -> str:
    vals = [r[key] for r in rows if r.get(key) is not None]
    if not vals:
        return f"n={len(rows)} {key}: none mature"
    t = sum(1 for v in vals if v >= TAIL)
    lose = sum(1 for v in vals if v < 0)
    return (f"n={len(rows)} mature={len(vals)} tail>=+20%={t} ({t/len(vals)*100:.1f}%) "
            f"losers(<0)={lose} losers-per-tail={lose/t if t else float('inf'):.1f} "
            f"median={statistics.median(vals)*100:+.1f}% best={max(vals)*100:+.1f}%")


def r_stats(rs: list[float]) -> str:
    if not rs:
        return "no settled R"
    return (f"settled n={len(rs)} sum={sum(rs):+.1f}R mean={statistics.mean(rs):+.2f}R "
            f"median={statistics.median(rs):+.2f}R best={max(rs):+.2f}R worst={min(rs):+.2f}R "
            f">=2R={sum(1 for x in rs if x >= 2)} >=4R={sum(1 for x in rs if x >= 4)} "
            f"losers(<0)={sum(1 for x in rs if x < 0)}")


# ── main ──────────────────────────────────────────────────────────────────────────────────────
def main() -> None:
    cap1 = parse_aligned(CAP1)
    p2 = ep_replay.read_sections(ep_replay.DATA / "_pull2_out.txt")
    daily = ep_replay.load_daily()
    trades_all = [t for t in p2["TRADES"] if t["signal_type"] == "magna53" and t["status"] == "closed"]
    trades = [t for t in trades_all if t["entry_attempt"] == "1"]
    alerts = p2["ALERTS"]
    camp = parse_tsv_pipe(CAMP, CAMP.read_text().splitlines()[0].split("|"))[1:]
    ladder = parse_tsv_pipe(LADDER, ["ticker", "alert_date", "source", "skip_category", "skip_reason", "ep_score",
                                     "gap_pct", "catalyst_quality", "ret_1d", "ret_5d", "ret_20d",
                                     "max_high_5d", "max_high_20d"])
    cap2 = parse_psv(CAP2) if CAP2.exists() else None

    print("#545 PHASE 2 — MISSED-EP TAIL READ — offline reader output (generated "
          f"{datetime.now().strftime('%Y-%m-%d %H:%M')} local)")
    print(f"capture 1: {CAP1.name} · campaigns: {CAMP.name} ({len(camp)} rows) · ladder: {LADDER.name} "
          f"({len(ladder)} rows) · capture 2: {'PRESENT' if cap2 else 'ABSENT — era/security-type split and August ret_5d NOT available'}")
    print("UNITS: every ret_* here is a FRACTION printed as %; tail bar = ret_20d >= 0.20; max_high_* is MFE, never a return.\n")

    # ── §A THE PASS BAR — the traded cohort on the SAME proxy ────────────────────────────────
    print("=" * 100)
    print("§A  PASS BAR — the traded cohort's own share on the daily-grain proxy ((close_d20 − open_d0)/open_d0 ≥ +20%)")
    print("=" * 100)
    live = [t for t in trades if t["account_mode"] == "live"]
    paper = [t for t in trades if t["account_mode"] == "paper"]
    for label, pool in (("26 closed LIVE trades (real money, first attempts)", live),
                        ("closed PAPER trades (first attempts)", paper)):
        rows = []
        for t in pool:
            d = date.fromisoformat(t["alert_date"])
            px = daily_proxy(daily, t["ticker"], d)
            risk = _f(t["risk_dollars_actual"]) or _f(t["risk_dollars"])
            pnl = _f(t["total_pnl"])
            rows.append({**px, "ticker": t["ticker"], "d": d,
                         "r": (pnl / risk) if (risk and pnl is not None) else None})
        print(f"\n{label}: {tail_stats(rows)}")
        print(f"   same rows, ret_5d proxy: {tail_stats(rows, 'ret_5d')}")
        rs = [r["r"] for r in rows if r["r"] is not None]
        print(f"   realized R (total_pnl / COALESCE(risk_actual, risk)): {r_stats(rs)}")
        print("   CONVERSION — proxy tail vs what the bracket realized on the same name:")
        for r in sorted(rows, key=lambda x: -(x["ret_20d"] if x["ret_20d"] is not None else -9)):
            if r["ret_20d"] is not None and r["ret_20d"] >= TAIL:
                print(f"      {r['ticker']:6} {r['d']}  proxy ret_20d {r['ret_20d']*100:+6.1f}%  "
                      f"ret_5d {(r['ret_5d'] or 0)*100:+6.1f}%  realized {r['r']:+.2f}R" if r["r"] is not None else
                      f"      {r['ticker']:6} {r['d']}  proxy ret_20d {r['ret_20d']*100:+6.1f}%  realized n/a")
        n_tail = sum(1 for r in rows if r["ret_20d"] is not None and r["ret_20d"] >= TAIL)
        n_tail_r4 = sum(1 for r in rows if r["ret_20d"] is not None and r["ret_20d"] >= TAIL
                        and r["r"] is not None and r["r"] >= 4)
        n_tail_r2 = sum(1 for r in rows if r["ret_20d"] is not None and r["ret_20d"] >= TAIL
                        and r["r"] is not None and r["r"] >= 2)
        print(f"   → of {n_tail} proxy-tail names, the bracket realized ≥4R on {n_tail_r4} and ≥2R on {n_tail_r2}.")

    # the admitted population — every live alert 05-11 → 08-31 (the names skipped buckets compete against)
    print("\n270 ADMITTED ALERTS (mi_ep_alerts live-source, 05-11 → 08-31) on the same proxy, by stored tier:")
    by_tier = defaultdict(list)
    for a in alerts:
        d = date.fromisoformat(a["alert_date"])
        by_tier[a["score_tier"] or "none"].append({**daily_proxy(daily, a["ticker"], d), "ticker": a["ticker"], "d": d})
    for tier in ("HIGH", "MODERATE", "none"):
        print(f"   {tier:9} {tail_stats(by_tier[tier])}")
    all_alerts = [r for v in by_tier.values() for r in v]
    print(f"   {'ALL':9} {tail_stats(all_alerts)}")
    gapped_alerts = [r for r in all_alerts if r["gapped"]]
    print(f"   ALL, gapped at the open (≥9% over the prior close, the #595 rule) — the like-for-like comparator:")
    print(f"   {'GAPPED':9} {tail_stats(gapped_alerts)}   [not gapped: {sum(1 for r in all_alerts if r['gapped'] is False)}, no prior bar: {sum(1 for r in all_alerts if r['gapped'] is None)}]")
    # by month — the era split the pre-registration demands
    print("   by month (HIGH+MODERATE):")
    bym = defaultdict(list)
    for r in all_alerts:
        bym[r["d"].strftime("%Y-%m")].append(r)
    for m in sorted(bym):
        print(f"      {m}  {tail_stats(bym[m])}")

    # ── §B THE LIVE-BRACKET HALF — alert-level buckets through campaigns_era_c ───────────────
    print("\n" + "=" * 100)
    print("§B  LIVE-BRACKET HALF — every skipped ALERT walked through the CURRENT day-1 bracket (era_c: entry ORB high,")
    print("    stop entry−2R at half size, +2R partial, breakeven, SMA trail). Source: campaigns_era_c.tsv (validate PASS 09-02).")
    print("=" * 100)
    traded_live = {(t["ticker"], t["alert_date"]) for t in trades_all if t["account_mode"] == "live"}
    traded_paper = {(t["ticker"], t["alert_date"]) for t in trades_all if t["account_mode"] == "paper"}
    # three ticker-days carry two alert rows (ACMR 08-07, KMT 08-05, MANE 07-15) — one campaign each
    seen: set = set()
    camp = [c for c in camp if not ((c["ticker"], c["alert_date"]) in seen or seen.add((c["ticker"], c["alert_date"])))]
    # bucket map: capture 2's ALERT_LEVEL_ROWS is authoritative (to 09-01); the 08-14 ladder is the fallback
    bucket_of: dict[tuple[str, str], str] = {}
    bucket_src = "ladder (to 08-14)"
    for r in ladder:
        bucket_of[(r["ticker"], r["alert_date"])] = r["skip_category"]
    if cap2 and cap2.get("ALERT_LEVEL_ROWS"):
        bucket_of = {(r["ticker"], r["alert_date"]): r["skip_category"] for r in cap2["ALERT_LEVEL_ROWS"]}
        bucket_src = "capture 2 ALERT_LEVEL_ROWS (to 09-01)"
    for (tk, d) in STOP_TOO_WIDE:
        bucket_of.setdefault((tk, d.isoformat()), "stop_too_wide")
    print(f"bucket labels from: {bucket_src}; the 9 MAGNA53 stop_too_wide names from stop_too_wide_cohort.py")

    minutes = ep_replay.load_minutes()
    rs_c = ep_replay.get_ruleset("era_c")
    det = {(a["ticker"], a["alert_date"]): a["detected_at_et"] for a in alerts}

    def _submit(key):
        submit = time(9, 31)
        if det.get(key):
            t = datetime.fromisoformat(det[key]).time()
            submit = max(submit, time(t.hour, t.minute))
        return submit

    live_path: dict[tuple[str, str], dict] = {}
    for c in camp:
        key = (c["ticker"], c["alert_date"])
        live_path[key] = walk_live_path(ticker=c["ticker"], alert_date=date.fromisoformat(c["alert_date"]),
                                        rs=rs_c, minutes=minutes, daily=daily, submit=_submit(key))
    lp_changed = sum(1 for c in camp if (live_path[(c["ticker"], c["alert_date"])]["status"] != c["status"]
                     or (_f(c["realized_r"]) is not None and live_path[(c["ticker"], c["alert_date"])]["realized_r"] is not None
                         and abs(_f(c["realized_r"]) - live_path[(c["ticker"], c["alert_date"])]["realized_r"]) > 1e-6)))
    print(f"LIVE PARTIAL PATH variant (ladder partial stood down, as live does): {lp_changed} of {len(camp)} campaigns "
          f"differ from the harness path in status or R.")

    groups: dict[str, list[dict]] = defaultdict(list)
    for c in camp:
        key = (c["ticker"], c["alert_date"])
        if key in traded_live:
            g = "TRADED live (control)"
        elif key in traded_paper:
            g = "TRADED paper (control)"
        elif key in bucket_of:
            g = bucket_of[key]
        elif c["score_tier_stored"] == "HIGH":
            # a HIGH in neither a closed trade nor any skip bucket was TRADED in some other form — the EOD paper
            # simulator (mi_paper_trades, any status) or a live row still open at the horizon (MRNA 08-19, OKTA
            # 08-27) — missed_outcomes' `traded` CTE excludes those, so they are NOT a missed population
            g = "HIGH in no skip bucket (paper-EOD-sim or open live — NOT missed; label check via capture 2)"
        elif c["score_tier_stored"] == "MODERATE":
            g = "moderate_tier"
        else:
            g = "tier none (never a HIGH/MODERATE)"
        px = daily_proxy(daily, c["ticker"], date.fromisoformat(c["alert_date"]))
        lp = live_path[(c["ticker"], c["alert_date"])]
        groups[g].append({**c, **px, "lp_status": lp["status"], "lp_r": lp["realized_r"],
                          "lp_final": lp["final_reason"], "lp_partial": lp["partial_fired"]})

    order = sorted(groups, key=lambda g: (-len(groups[g]), g))
    for g in order:
        rows = groups[g]
        st = Counter(r["status"] for r in rows)
        adm = Counter(r["admit"] for r in rows)
        rs = [_f(r["realized_r"]) for r in rows if r["status"] == "settled" and _f(r["realized_r"]) is not None]
        print(f"\n[{g}]  campaigns={len(rows)}  status={dict(st)}  era_c re-admission={dict(adm)}")
        print(f"   daily proxy on these names: {tail_stats(rows)}")
        print(f"   …gapped at the open only:   {tail_stats([r for r in rows if r['gapped']])}")
        print(f"   bracket (harness path):      {r_stats(rs)}")
        lrs = [r["lp_r"] for r in rows if r["lp_status"] == "settled" and r["lp_r"] is not None]
        lst = Counter(r["lp_status"] for r in rows)
        print(f"   bracket (LIVE partial path): {r_stats(lrs)}  status={dict(lst)}")
        ent = [r for r in rows if r["entered"] == "True"]
        pf = sum(1 for r in ent if r["partial_fired"] == "True")
        print(f"   entered={len(ent)} partial_fired={pf} final={dict(Counter(r['final_reason'] for r in ent if r['final_reason']))}")
        # the bridge: proxy tail → bracket
        tails = [r for r in rows if r["ret_20d"] is not None and r["ret_20d"] >= TAIL]
        if tails:
            print("   proxy-tail names and what the bracket did with each:")
            for r in sorted(tails, key=lambda x: -x["ret_20d"]):
                rr = _f(r["realized_r"])
                lr = r["lp_r"]
                print(f"      {r['ticker']:6} {r['alert_date']}  proxy {r['ret_20d']*100:+6.1f}%  "
                      f"status={r['status']:15} {('R ' + format(rr, '+.2f')) if rr is not None else ('reason=' + (r['reason'] or ''))}"
                      f"{'  partial' if r['partial_fired']=='True' else ''}  final={r['final_reason'] or '-'}"
                      f"  | live path: {r['lp_status']} {('R ' + format(lr, '+.2f')) if lr is not None else ''}")

    # THE BRIDGE — every gapped-at-the-open alert that reached the proxy tail, and what the bracket did with it
    print("\n" + "-" * 100)
    print("BRIDGE — every admitted alert that (a) gapped ≥9% at the open and (b) reached ≥+20% at 20 sessions, with the")
    print("bracket's outcome. This is the conversion rate from 'proxy tail' to realized R that every bucket share must be read through.")
    print("-" * 100)
    allc = [r for g in groups.values() for r in g]
    bridge = [r for r in allc if r["gapped"] and r["ret_20d"] is not None and r["ret_20d"] >= TAIL]
    grp_of = {id(r): g for g, rows in groups.items() for r in rows}
    for r in sorted(bridge, key=lambda x: -x["ret_20d"]):
        rr = _f(r["realized_r"])
        print(f"   {r['ticker']:6} {r['alert_date']} {r['score_tier_stored']:8} proxy {r['ret_20d']*100:+6.1f}%  "
              f"{r['status']:15} {('R ' + format(rr, '+.2f')) if rr is not None else (r['reason'] or '')}  [{grp_of[id(r)][:28]}]")
    st = Counter(r["status"] for r in bridge)
    rs_b = [_f(r["realized_r"]) for r in bridge if r["status"] == "settled"]
    print(f"   → {len(bridge)} gapped proxy-tail alerts: status {dict(st)}; of the settled, ≥4R={sum(1 for x in rs_b if x >= 4)}, "
          f"≥2R={sum(1 for x in rs_b if x >= 2)}, sum={sum(rs_b):+.1f}R; unenterable by rule (window_out_of_orb)="
          f"{sum(1 for r in bridge if r['reason'] == 'window_out_of_orb')}")
    lrs_b = [r["lp_r"] for r in bridge if r["lp_status"] == "settled" and r["lp_r"] is not None]
    print(f"   → same 14 on the LIVE partial path: status {dict(Counter(r['lp_status'] for r in bridge))}; settled ≥4R="
          f"{sum(1 for x in lrs_b if x >= 4)}, ≥2R={sum(1 for x in lrs_b if x >= 2)}, sum={sum(lrs_b):+.1f}R")
    for r in sorted(bridge, key=lambda x: -x["ret_20d"]):
        if r["lp_status"] == "settled" or r["status"] == "settled":
            print(f"      {r['ticker']:6} harness {r['status']:9} {(_f(r['realized_r']) if _f(r['realized_r']) is not None else 0):+.2f}R"
                  f"   live path {r['lp_status']:15} {(r['lp_r'] if r['lp_r'] is not None else 0):+.2f}R {r['lp_final'] or ''}")

    # ── §C LEG PRINT — the prompting case and its bucket, checkable by hand ──────────────────
    print("\n" + "=" * 100)
    print("§C  LEG PRINT — stop_too_wide names re-walked with walk_campaign (era_c) so the number is checkable")
    print("=" * 100)
    for tk, d in sorted(STOP_TOO_WIDE, key=lambda x: x[1]):
        key = (tk, d.isoformat())
        if key not in det:
            print(f"\n{tk} {d}: not in the 270-alert capture (pre 05-11) — no minute bars, not walked")
            continue
        px = daily_proxy(daily, tk, d)
        for label, walker in (("HARNESS path (ladder partial on)", ep_replay.walk_campaign),
                              ("LIVE partial path (ladder stood down)", walk_live_path)):
            res = walker(ticker=tk, alert_date=d, rs=rs_c, minutes=minutes, daily=daily, submit=_submit(key))
            print(f"\n{tk} {d} [{label}]: status={res['status']} reason={res['reason']} entered={res['entered']} "
                  f"entry={res['entry_px']} stop={res['stop']} target={res['target']} "
                  f"realized={res['realized_r'] if res['realized_r'] is None else format(res['realized_r'], '+.2f')}R "
                  f"| daily proxy ret_5d={(px['ret_5d'] or 0)*100:+.1f}% ret_20d={'n/a' if px['ret_20d'] is None else format(px['ret_20d']*100, '+.1f')+'%'} "
                  f"MFE20={'n/a' if px['max_high_20d'] is None else format(px['max_high_20d']*100, '+.1f')+'%'}")
            for e in res["exits"]:
                print(f"      {e['reason']:15} {str(e['time'])[:16]:16} px={e['price']:.4f} shares={e['shares']:.4f} pnl={e['pnl']:+.4f}")
            if res["status"] == "no_entry":
                break

    # HTFL by hand on the LIVE partial path: the harness books the day-3 ladder partial (exit_logic.py:336), but live
    # stands that branch down while the intraday +2R trigger is on (live_tracker.py:1076, skip_partial_decision=
    # bool(PROFIT_TRIGGER_R)) — live would instead sell 1/3 at the +2R target the first session the HIGH reaches it,
    # then trail the rest on the stock's own MA (independent of our partial), so the remainder exits where the harness's did.
    hb = daily.get("HTFL", {})
    entry, stop, target = 39.06, 33.96, 44.16
    hit = next((d for d in sorted(hb) if d >= date(2026, 8, 14) and hb[d]["h"] is not None and hb[d]["h"] >= target), None)
    if hit:
        rest_px = 47.416   # the harness's trail exit on 08-31 (same MA, same day)
        pnl = (target - entry) / 3 + (rest_px - entry) * 2 / 3
        print(f"\nHTFL on the LIVE partial path (hand walk): +2R target {target} first reached {hit} "
              f"(high {hb[hit]['h']}); 1/3 at {target}, 2/3 at the same trail exit {rest_px} on 08-31 → "
              f"{pnl:+.3f} per share / {entry-stop:.2f} risk = {pnl/(entry-stop):+.2f}R  (harness: +1.28R; either way < 2R, "
              f"and the ORB-range R of the recorder would read ×2 = {2*pnl/(entry-stop):+.2f}R on the ORB unit)")

    # ── §D CAPTURE 2 — era / security-type split, ret_5d beside ret_20d ──────────────────────
    print("\n" + "=" * 100)
    print("§D  CAPTURE 2 — per bucket: pooled vs CURRENT-SCAN population (drop pre-04-20 rows and non-common-stock)")
    print("=" * 100)
    if not cap2:
        print("ABSENT. Run the command in _545p2_capture2.sql, then re-run this reader. Until then every scan-level")
        print("bucket verdict is PROVISIONAL: capture 1's pooled shares include pre-04-20 leveraged-ETF rows.")
    else:
        bm = cap2["BUCKET_MONTH"]
        def agg(rows):
            s = Counter()
            for r in rows:
                for k in ("n", "sessions", "n20", "tail20", "lose20", "n5", "tail5_20", "tail5_10", "lose5",
                          "day0_red", "tail20_day0red", "tail5_day0red", "gap_gt100"):
                    s[k] += int(r[k])
            return s
        buckets = sorted({r["skip_category"] for r in bm}, key=lambda b: -sum(int(r["n"]) for r in bm if r["skip_category"] == b))
        print("\nPer bucket — POOLED (all gapped rows) vs CURRENT-SCAN (alert_date ≥ 04-20 AND security type CS/ADRC or CS_by_sector):")
        print(f"{'bucket':20} {'pop':8} {'n':>5} {'n20':>5} {'tail20':>7} {'share':>6} {'lose/tail':>9} {'n5':>5} {'tail5':>6} {'share5':>7} {'day0red':>8} {'sess':>5} {'per-sess':>8}")
        for b in buckets:
            rows_b = [r for r in bm if r["skip_category"] == b]
            cur_b = [r for r in rows_b if r["pre_sectype_filter"] == "f" and r["cls"] in ("CS", "CS_by_sector")]
            for lab, rows in (("pooled", rows_b), ("current", cur_b)):
                s = agg(rows)
                sh = f"{s['tail20']/s['n20']*100:.1f}%" if s["n20"] else "-"
                sh5 = f"{s['tail5_20']/s['n5']*100:.1f}%" if s["n5"] else "-"
                lpt = f"{s['lose20']/s['tail20']:.1f}" if s["tail20"] else "inf"
                print(f"{b:20} {lab:8} {s['n']:5} {s['n20']:5} {s['tail20']:7} {sh:>6} {lpt:>9} {s['n5']:5} {s['tail5_20']:6} {sh5:>7} {s['day0_red']:8} {s['sessions']:5} {s['n']/s['sessions'] if s['sessions'] else 0:8.2f}")
        print("\nPer bucket × month, CURRENT-SCAN population only (ret_20d tail | ret_5d tail):")
        for b in buckets:
            cur_b = [r for r in bm if r["skip_category"] == b and r["pre_sectype_filter"] == "f" and r["cls"] in ("CS", "CS_by_sector")]
            months = sorted({r["mon"] for r in cur_b})
            parts = []
            for m in months:
                s = agg([r for r in cur_b if r["mon"] == m])
                parts.append(f"{m[:7]}: n={s['n']} 20d {s['tail20']}/{s['n20']} · 5d {s['tail5_20']}/{s['n5']}")
            print(f"   {b:20} " + " | ".join(parts))
        print("\nSecurity-type classification of the TAIL rows (≥+20% at 5 or 20 sessions), per bucket:")
        tr = cap2["TAIL_ROWS"]
        for b in buckets:
            rows = [r for r in tr if r["skip_category"] == b]
            if not rows:
                continue
            c = Counter((r["cls"], "pre-04-20" if r["alert_date"] < "2026-04-20" else "post") for r in rows)
            print(f"   {b:20} n={len(rows):3} {dict(c)}")
        noncs = [r for r in tr if r["cls"] == "nonCS" or r["alert_date"] < "2026-04-20"]
        print(f"\n   tail rows that are non-common-stock OR pre-04-20: {len(noncs)} of {len(tr)} — tickers: "
              + ", ".join(sorted({r['ticker'] for r in noncs})))
        print("\nTRADED_PROXY cross-check (prod LATERAL vs this reader's local replica):")
        for r in cap2["TRADED_PROXY_ROWS"]:
            loc = daily_proxy(daily, r["ticker"], date.fromisoformat(r["alert_date"]))
            a, b_ = _f(r["ret_20d"]), loc["ret_20d"]
            flag = "" if (a is None and b_ is None) or (a is not None and b_ is not None and abs(a - b_) < 1e-6) else "  ⚠ MISMATCH"
            if flag or (a is not None and a >= TAIL):
                print(f"   {r['ticker']:6} {r['alert_date']} {r['account_mode']:5} prod ret_20d={a} local={b_}{flag}")
        print(f"\nOVERLAP: {cap2['OVERLAP'][0]['ticker_days_in_2plus_buckets']} gapped ticker-days sit in 2+ buckets — never sum buckets.")
        print("HTFL rows:")
        for r in cap2["HTFL"]:
            print("   " + " ".join(f"{k}={v}" for k, v in r.items()))


if __name__ == "__main__":
    buf = io.StringIO()
    with redirect_stdout(buf):
        main()
    text = buf.getvalue()
    OUT.write_text(text)
    sys.stdout.write(text)
    sys.stdout.write(f"\nwritten: {OUT}\n")
