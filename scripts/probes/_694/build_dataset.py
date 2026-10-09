#!/usr/bin/env python3
"""#694 tie-breaker test — raw captured pulls -> ONE per-row dataset (dataset.csv).

READ-ONLY, LOCAL, NO NETWORK. Reads only the files captured once from prod (q*.out) plus the
two label fixtures in tests/fixtures/. Writes dataset.csv, labels_snapshot.csv and
build_checks.txt next to this file.

Pool rule (pinned from q02_ticks.out / q03_pool.sql): every mi_ep_scan_log row with
rank_by_gap NOT NULL (= the candidate reached the shortlist sort) at each day's LAST pre-open
tick (max scan_time_et < 09:30 ET among ranked rows). April 13-30 rows carry no tick and no
rank (logged once per name per day), so April has no pool.

Keys, all "higher = ranked first" unless stated, each computed ONLY from data that existed
before the 09:25-ish tick:
  k1_adv_dollar   20-day ADV shares (mi_stock_scores.adv_20 at P) x the scan row's prev_close.
                  P = latest COMPLETE score_date on or before scan_date - 1 day, using the real
                  db._pick_latest_complete_score_date (what fix (b) will read). adv_20 0/NULL ->
                  missing (get_adv_map drops falsy values). NEVER the scan row's own adv.
  k2_pm_dollar    pre-market volume so far x tick price. today_volume x current_price where
                  both were logged (from 2026-08-29); before that DERIVED as rel_volume x adv
                  (the row's own pair — rel_volume was computed as today_volume / that adv)
                  x prev_close x (1 + gap_pct/100). k2_src says which.
  k3_pm_rvol      the row's own pm_rvol (pre-market volume vs this ticker's normal at this
                  clock minute). Only written for names the grading loop reached; NOT imputed.
  k4_rs_composite mi_stock_scores.rs_composite at P (higher better).
  k4_rs_rank      mi_stock_scores.rs_rank at P (LOWER better; 1 = strongest).
  k5_zones        n_cleared from scripts/probes/_533_nbis_structure_encoder.encode(preopen=True)
                  UNCHANGED, fed a daily history whose scan-day row is a synthetic
                  (d, px, px, px, px, 0) with px = tick price — so neither the real open nor the
                  real day high can leak in. Daily history from 2025-07-07 (the window the
                  encoder's 8-fixture gate was calibrated on). Computed only on zones_days.txt.
  k6_gap          gap_pct as logged (the CONTROL).
Theme flag: the logged in_active_theme where present (from 2026-08-29); otherwise rebuilt from
mi_themes (latest row per theme name with theme_date in [d-7, d-1], latest not Retired, stage in
Accelerating/Mainstream, ticker in its list). Agreement with the logged flag is checked.
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE.parent))

from agents.market_intelligence.db import _pick_latest_complete_score_date  # noqa: E402  pure fn
from tests.fixtures.must_not_miss_eps import MUST_NOT_MISS  # noqa: E402
from tests.fixtures.must_not_trade_charts import CHART_RULINGS  # noqa: E402
import _533_nbis_structure_encoder as nbis  # noqa: E402  encode() reused UNCHANGED

LABEL_FLOOR = "2026-04-13"
DAILY_FROM = "2025-07-07"
THEME_STAGES = ("Accelerating", "Mainstream")
checks: list[str] = []


def f(x):
    try:
        return float(x) if x not in ("", None) else None
    except ValueError:
        return None


def read_psql(path: Path) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as fh:
        rd = csv.DictReader(fh, delimiter="|")
        for r in rd:
            first = next(iter(r.values()))
            if first is None or first.startswith("("):
                continue
            rows.append(r)
    return rows


# ── labels ─────────────────────────────────────────────────────────────────────────────
labels: dict[tuple[str, str], str] = {}
for m in MUST_NOT_MISS:
    if m.alert_date >= LABEL_FLOOR:
        labels[(m.ticker, m.alert_date)] = "REAL_EP"
for c in CHART_RULINGS:
    if c.verdict in ("GOOD_CHART", "OKISH_CHART", "BAD_CHART"):
        k = (c.ticker, c.alert_date)
        if k in labels and labels[k] != c.verdict:
            checks.append(f"LABEL CLASH {k}: {labels[k]} vs {c.verdict} (kept REAL_EP)")
            continue
        labels.setdefault(k, c.verdict)
with open(HERE / "labels_snapshot.csv", "w", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["ticker", "date", "label"])
    for (t, d), v in sorted(labels.items(), key=lambda x: (x[0][1], x[0][0])):
        w.writerow([t, d, v])
checks.append(f"labels: REAL_EP={sum(v=='REAL_EP' for v in labels.values())} "
              f"GOOD={sum(v=='GOOD_CHART' for v in labels.values())} "
              f"OKISH={sum(v=='OKISH_CHART' for v in labels.values())} "
              f"BAD={sum(v=='BAD_CHART' for v in labels.values())}")

# ── pool ───────────────────────────────────────────────────────────────────────────────
pool = read_psql(HERE / "q03_pool.out")
checks.append(f"pool rows={len(pool)} days={len({r['scan_date'] for r in pool})}")

# ── score dates: P = latest complete score_date <= scan_date - 1 ──────────────────────
counts = [(date.fromisoformat(r["score_date"]), int(r["n"]))
          for r in read_psql(HERE / "q07_score_counts.out")]
counts.sort(reverse=True)


def prior_complete(scan_d: str) -> str | None:
    bound = date.fromisoformat(scan_d) - timedelta(days=1)
    sub = [(d, n) for d, n in counts if d <= bound][:40]
    p = _pick_latest_complete_score_date(sub)
    return p.isoformat() if p else None


scores: dict[tuple[str, str], dict] = {}
for r in read_psql(HERE / "q08_scores.out"):
    scores[(r["ticker"], r["score_date"])] = r

# ── themes (rebuild for days before the scan log carried the flag) ─────────────────────
theme_rows = read_psql(HERE / "q09_themes.out")
by_name: dict[str, list[tuple[str, str, set[str]]]] = defaultdict(list)
for r in theme_rows:
    by_name[r["name"]].append((r["theme_date"], r["stage"], set(filter(None, r["tickers"].split(",")))))
for v in by_name.values():
    v.sort(key=lambda x: x[0])
_theme_cache: dict[str, set[str]] = {}


def theme_set(scan_d: str) -> set[str]:
    if scan_d in _theme_cache:
        return _theme_cache[scan_d]
    d = date.fromisoformat(scan_d)
    lo, hi = (d - timedelta(days=7)).isoformat(), (d - timedelta(days=1)).isoformat()
    out: set[str] = set()
    for name, snaps in by_name.items():
        latest = None
        for td, st, tks in snaps:
            if lo <= td <= hi:
                latest = (td, st, tks)
        if latest and latest[1] != "Retired" and latest[1] in THEME_STAGES:
            out |= latest[2]
    _theme_cache[scan_d] = out
    return out


# ── daily history for key 5 ────────────────────────────────────────────────────────────
zones_days = set((HERE / "zones_days.txt").read_text().split())
daily: dict[str, list] = defaultdict(list)
with open(HERE / "q10_daily.out", encoding="utf-8") as fh:
    for ln in fh:
        p = ln.rstrip("\n").split("|")
        if len(p) != 7 or p[1] < DAILY_FROM:
            continue
        o, h, lo_, c, v = (f(x) for x in p[2:7])
        if None in (o, h, lo_, c) or c <= 0 or h <= 0:
            continue
        daily[p[0]].append((p[1], o, h, lo_, c, v or 0.0))
for t in daily:
    daily[t].sort()


def zones_cleared(ticker: str, d: str, px: float | None) -> tuple[int | None, str]:
    if px is None or px <= 0:
        return None, "no_tick_price"
    hist = [row for row in daily.get(ticker, []) if row[0] < d]
    if not hist:
        return None, "no_daily_history"
    synth = {ticker: hist + [(d, px, px, px, px, 0.0)]}
    r = nbis.encode(ticker, d, synth, {}, preopen=True)
    if r.get("error"):
        return None, r["error"]
    return int(r["n_cleared"]), r.get("cls", "")


# ── assemble ───────────────────────────────────────────────────────────────────────────
out = []
p_by_day: dict[str, str | None] = {}
k2_check = []          # (logged today_volume, derived) on rows that have both
price_check = []
theme_agree = [0, 0]
for r in pool:
    d, t = r["scan_date"], r["ticker"]
    if d not in p_by_day:
        p_by_day[d] = prior_complete(d)
    P = p_by_day[d]
    s = scores.get((t, P)) if P else None
    prev_close, gap = f(r["prev_close"]), f(r["gap_pct"])
    adv20 = f(s["adv_20"]) if s else None
    k1 = adv20 * prev_close if (adv20 and prev_close) else None

    rel, adv = f(r["rel_volume"]), f(r["adv"])
    tv_logged, cp_logged = f(r["today_volume"]), f(r["current_price"])
    tv_derived = rel * adv if (rel is not None and adv) else None
    cp_derived = prev_close * (1 + gap / 100.0) if (prev_close and gap is not None) else None
    if tv_logged is not None and tv_derived is not None:
        k2_check.append((tv_logged, tv_derived, rel))
    if cp_logged is not None and cp_derived is not None:
        price_check.append((cp_logged, cp_derived))
    if tv_logged is not None and cp_logged is not None:
        k2, k2_src, px = tv_logged * cp_logged, "logged", cp_logged
    else:
        k2 = tv_derived * cp_derived if (tv_derived is not None and cp_derived) else None
        k2_src, px = "derived", cp_derived

    rebuilt_theme = t in theme_set(d)
    if r["in_active_theme"] in ("t", "f"):
        theme = r["in_active_theme"] == "t"
        theme_src = "logged"
        theme_agree[0] += int(theme == rebuilt_theme)
        theme_agree[1] += 1
    else:
        theme, theme_src = rebuilt_theme, "rebuilt"

    if d in zones_days:
        k5, k5_note = zones_cleared(t, d, px)
    else:
        k5, k5_note = None, "not_computed_day"

    out.append({
        "scan_date": d, "ticker": t, "tick_et": r["tick_et"], "pool": 1,
        "label": labels.get((t, d), ""),
        "rank_by_gap_logged": r["rank_by_gap"], "rank_by_prescore_logged": r["rank_by_prescore"],
        "reject_stage": r["reject_stage"], "filter_reason": r["filter_reason"][:80],
        "prev_close": prev_close, "gap_pct": gap, "tick_price": px,
        "in_theme": int(theme), "theme_src": theme_src,
        "score_date_P": P, "adv20_P": adv20,
        "k1_adv_dollar": k1, "k2_pm_dollar": k2, "k2_src": k2_src,
        "k3_pm_rvol": f(r["pm_rvol"]),
        "k4_rs_composite": f(s["rs_composite"]) if s else None,
        "k4_rs_rank": f(s["rs_rank"]) if s else None,
        "k5_zones": k5, "k5_note": k5_note, "k6_gap": gap,
    })

# labelled pairs NOT in their day's pool — counted out, carried as pool=0 rows
in_pool = {(o["ticker"], o["scan_date"]) for o in out}
for (t, d), v in sorted(labels.items(), key=lambda x: (x[0][1], x[0][0])):
    if (t, d) not in in_pool:
        out.append({"scan_date": d, "ticker": t, "pool": 0, "label": v})

cols = ["scan_date", "ticker", "tick_et", "pool", "label", "rank_by_gap_logged",
        "rank_by_prescore_logged", "reject_stage", "filter_reason", "prev_close", "gap_pct",
        "tick_price", "in_theme", "theme_src", "score_date_P", "adv20_P", "k1_adv_dollar",
        "k2_pm_dollar", "k2_src", "k3_pm_rvol", "k4_rs_composite", "k4_rs_rank", "k5_zones",
        "k5_note", "k6_gap"]
with open(HERE / "dataset.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=cols)
    w.writeheader()
    for o in out:
        w.writerow({k: ("" if o.get(k) is None else o.get(k, "")) for k in cols})

# ── build checks ───────────────────────────────────────────────────────────────────────
checks.append("prior complete score_date P per pool day (scan_date -> P):")
checks.append("  " + " ".join(f"{d}->{p}" for d, p in sorted(p_by_day.items())))
bad_p = [d for d, p in p_by_day.items() if p is None or p >= d]
checks.append(f"  days with no P or P >= scan_date (lookahead): {bad_p or 'none'}")
if k2_check:
    import statistics as st
    rel_err = [abs(a - b) / a for a, b, _ in k2_check if a > 0]
    within = sum(1 for a, b, rl in k2_check if a > 0 and abs(a - b) / a <= 0.25)
    checks.append(f"k2 derivation check on {len(k2_check)} rows with both logged and derived "
                  f"pre-market volume: median relative error {st.median(rel_err):.3f}; "
                  f"{within} of {len(rel_err)} within 25%")
if price_check:
    pe = [abs(a - b) / a for a, b in price_check if a]
    checks.append(f"tick-price derivation check on {len(pe)} rows: max relative error {max(pe):.4f}")
checks.append(f"theme flag: logged vs rebuilt agree on {theme_agree[0]} of {theme_agree[1]} rows "
              f"(rows from 2026-08-29 that carry the logged flag)")
zn = [o for o in out if o.get("pool") == 1 and o["scan_date"] in zones_days]
checks.append(f"k5 zones: {sum(1 for o in zn if o['k5_zones'] is not None)} of {len(zn)} rows on "
              f"{len(zones_days)} zones days computed; failures: "
              + str(dict(__import__('collections').Counter(o['k5_note'] for o in zn if o['k5_zones'] is None))))
(HERE / "build_checks.txt").write_text("\n".join(checks) + "\n")
print("\n".join(checks))
print(f"wrote dataset.csv rows={len(out)}")
