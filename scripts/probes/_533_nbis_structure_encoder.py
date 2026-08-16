#!/usr/bin/env python3
"""NBIS STRUCTURE ENCODER — "neglected stock gapping through key levels", encoded from
the operator's OWN falsifiable definition (notes 2026-08-12 NBIS), fixture-gated on his
OWN labelled reads before anything is swept. (READ-ONLY probe; SHADOW ONLY; no writes,
no trading, no LLM spend, nothing wired into any live path.)

Spec: docs/roadmap/ep_profitability_program.md §2 "THE NBIS ENCODING". Supersedes the
rejected crude proxy (_533_structure_admission_probe.py, "above all three SMAs") that he
pushed back on 2026-08-12: *"chart structure is part science part art... sometimes you go
further back because we see multiple tests of certain levels that failed previously,
sometimes you don't."*

THE DEFINITION, DECOMPOSED (his, verbatim sources in operator_shared_notes.md):
 1. A LEVEL THAT PREVIOUSLY REJECTED PRICE.  Three classes:
    (a) merged pivot highs — daily local maxima (+-2-day window) merged within 0.3%
        (the RMVP developer's merge parameter, notes 2026-06-30), QUALIFIED only when
        tested >=2 times in >=2 separate EPISODES: a test = a day whose high came within
        0.5xADR20 below the level (or poked above) and failed to close above it; two
        tests are separate EPISODES only if price was genuinely REJECTED between them
        (some intervening low >=1.0xADR20 below the level) — chop hugging a line is ONE
        test, not several.  A level DIES when a daily close breaks above it; only tests
        after the last break count.
    (b) the 50-day SMA — counted ONLY when it actually acted as resistance: >=2 failed
        test episodes against the SMA path within the CURRENT below-the-SMA regime.
        NBIS's 50-day mattered *because* it was rejecting price, not because it is an MA.
    (c) the 52-week / available-history high — the HTFL/ETON "nothing overhead" case,
        its own class (a single ATH print is NOT congestion; it is the absence of it).
    THE LOOKBACK IS DERIVED, NOT FIXED: levels are formed over the FULL available daily
    history and each level's own test dates determine how far back it reaches.  A name
    whose failed tests sit 6 months back gets a 6-month lookback; a name with none gets
    none.  This is the direct answer to his "sometimes you go further back" objection —
    there is no window parameter to tune.
 2. DID THE GAP CLEAR IT — the open prints above the level, OR a 5-minute close above
    it within the first 30 minutes (the opening drive of the gap; NBIS itself opened
    $0.81 UNDER the $226.8 prior-highs level and closed above it 19 minutes in — his
    read still says "gapped up through previous highs").  Open-only where minutes are
    missing (flagged).
 3. DID IT HOLD AFTER THE FIRST PULLBACK — his words are an END-STATE test: "pulled
    back and HELD UP in the early morning" (a dip below-and-reclaim is a HOLD — NBIS
    dipped under the 50-day in minutes 1-5 and reclaimed) vs "drop and HELD BELOW those
    points" (settled below = lost).  Operationalised: the last 5-minute close of the
    window vs the cleared level.  Windows swept 60 min (10:30) / 120 min (11:30) /
    rest-of-morning (12:00 ET); PRIMARY = 60 min ("the early morning").
 4. THE TWO FAILURE CLASSES, his words: *"drop and held below those points"* =
    CLEARED_LOST (end-state below); *"gap and not breach those points"* =
    NEVER_BREACHED (no breach in the first 30 min).
 ⚠ v1 of this encoder read CLEAR as "open above + first-5m-close above" and HOLD as
    "no 5-min close ever below" — both stricter than his words, and v1 failed NBIS ON
    HIS OWN WORKED EXAMPLE (open $0.81 under the level; early dip under the 50-day).
    The v2 semantics above are the correction, made against the fixture set BY DESIGN
    (the fixtures are the calibration set; the sweep is the out-of-sample read).
 5. CONGESTION — *"it just gaps into congestion, resistance areas and had no strength
    to break through"*: how much overhead supply sits in the 1.5xADR20 band above the
    open (the RMVP ADR multiplier): prior-day closes in the band (full history AND last
    60 days), % of last-60 closes above the open, and any QUALIFIED uncleared level
    inside the band.

CLASSES: BLUE_SKY_HELD/LOST (open above every prior high) · CLEARED_HELD/LOST (cleared
>=1 qualified level) · NEVER_BREACHED (a qualified overhead level the gap did not clear)
· NEAR_ATH (no qualified overhead level, history high within 1.5xADR of the open) ·
NO_LEVEL (no qualified overhead level, not near the high — judged on congestion alone;
the VERA shape: nothing meaningful was cleared and supply sits overhead).

VERDICT (binary, for the fixture table): GOOD = the gap cleared real overhead (or had
none to clear) AND held it at the window end AND is not still buried under its own
recent history (the "deep in its downtrend" override: >=70% of the last 60 closes above
the open vetoes — VERA 88%, vs EROC 49% which he called GOOD).  Congestion metrics are
always reported per name; the 70% cap and the 30-min breach window are the two
FIXTURE-CALIBRATED numbers, disclosed as such — the fixtures are the calibration set by
design (the house known-good-cohort move); the population sweep is the out-of-sample
read.  Note his EROC/HTFL labels rule out congestion-count vetoes: an old thin ATH
double-top (HTFL, last tested 10 months back) and a 3-week-old overhead shelf (EROC)
did not stop him calling structure good — what vetoes is never breaching, losing the
level, or gapping inside a chart that is mostly overhead.

🔴 FIXTURE GATE (hard, ordered): the encoder must FIRST reproduce the operator's 8
labelled reads — POSITIVE: NBIS 08-12 · HTFL 08-14 · ETON 08-14 · EROC 08-12 · SE 08-11;
NEGATIVE: VERA 08-14 · BW 08-11 · FRMI 08-11.  If it cannot, the probe SAYS SO AND
STOPS — no sweep, no distribution.  VERA is the load-bearing case: a positive-looking
gap that is structurally weak; an encoder that calls VERA good is measuring "it went
up", not structure.

SCALE GUARD (house lesson, stop_width_replay 2026-08-03): mi_daily_closes is
retroactively split-adjusted; mi_intraday_bars is as-traded at capture.  Per ticker-day
the minute open is checked against the daily open (2% tolerance); mismatches are
excluded from minute-dependent checks and counted, never rescaled.

POPULATION SWEEP (ONLY if the gate passes) — pre-registered battery, declared before
any outcome was read:
  PRIMARY    GOOD vs POOR verdict (daily-only Tier-B encoding: open-clear, no hold —
             the largest settled cohort) on ret_5d from alert-day open, permutation
             test shuffling whole SESSIONS (house convention — same-morning alerts
             share the tape).
  secondary  (descriptive, Bonferroni-noted): mfe_5d · ret_1d · the full-encoding
             Tier-A subset (minutes, since 07-28) · per-class table · a gap-band
             control (is the verdict just gap size in disguise).
A null is a real deliverable; this probe does not hunt for a positive.

THE LINE: this probe MEASURES.  Grading, admission, entry are detection criteria — the
operator's SOLE authority.  Nothing here gates, filters, scores or influences any alert,
entry or exit; promotion of this feature is fork S-3 (CHANGE_PROCESS + sign-off).

Phases (local TSVs beside this file, re-runnable offline — the _468/_533/_stopgeom shape):
  --pull       ssh read-only psql SELECTs -> _533n_alerts.tsv, _533n_daily.tsv,
               _533n_minute.tsv, _533n_scores.tsv   (capture once, read many)
  --fixtures   the 8-name fixture table + the gate verdict (run FIRST; capture to
               docs/analysis/structure_encoding_2026-08-15.txt)
  --sweep      population encoding + outcome read (REFUSES to run unless --fixtures
               passed in this same working tree: reads _533n_gate.json)
"""
from __future__ import annotations

import json
import random
import statistics as st
import subprocess
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
HOST = "apollo@87.99.134.162"
ALERTS_TSV = HERE / "_533n_alerts.tsv"
DAILY_TSV = HERE / "_533n_daily.tsv"
MINUTE_TSV = HERE / "_533n_minute.tsv"
SCORES_TSV = HERE / "_533n_scores.tsv"
GATE_JSON = HERE / "_533n_gate.json"

RANDOM_SEED = 20260815
N_PERM = 20000

# ── The definition's parameters (all from HIS shared sources, none fitted) ─────────────
PIVOT_WING = 2            # local max over +-2 days
MERGE_PCT = 0.3           # RMVP "Merge Within %" (notes 2026-06-30)
TEST_PROX_ADR = 0.5       # a test approaches within 0.5xADR20 below the level
REJECT_ADR = 1.0          # episodes separated only by a >=1xADR20 rejection
BAND_ADR = 1.5            # RMVP "ADR Multiplier" — the congestion band above the open
CLOSE_TOL = 1.001         # "failed to close above" tolerance (0.1%)
HOLD_TOL = 0.999          # a 5-min close below level*0.999 = lost it
MIN_HISTORY = 30          # fewer prior days than this -> insufficient_history
ADR_LOOKBACK = 20         # RMVP "ADR Lookback"

# ── The three FIXTURE-CALIBRATED numbers (disclosed; fixtures are the calibration set) ─
BREACH_CUTOFF = "09:59"   # the opening drive: a 5-min close above the level by here
                          # counts as the gap clearing it (NBIS breached $226.8 at 09:49)
MAX_C3_PCT = 70.0         # "deep in its downtrend" veto: >=70% of last-60 closes above
                          # the open = the gap landed inside its own recent supply
                          # (VERA 88.3% vs EROC 48.8% which he labelled GOOD)
MARGIN_ADR = 0.25         # "through, not onto": a level (or an overhead MA) only counts
                          # as CLEARED-AND-HELD if the window-end close stands at least a
                          # quarter of a day's range ABOVE it.  NBIS ended 0.46 ADR over
                          # its 50-day (through); FRMI ended 0.12 ADR over its 50-day
                          # (landed ON it — "below every moving average" pre-gap, dead)

FIXTURES = [  # (ticker, alert_date, operator_label, his words)
    ("NBIS", "2026-08-12", "GOOD", "gapped through the 50d + prior highs ~$227, held"),
    ("HTFL", "2026-08-14", "GOOD", "clearing key levels near or above ATH"),
    ("ETON", "2026-08-14", "GOOD", "clearing key levels near or above ATH"),
    ("EROC", "2026-08-12", "GOOD", "good structure (08-15 label; thin 44d history)"),
    ("SE",   "2026-08-11", "GOOD", "gapped through while above all MAs, decent base"),
    ("VERA", "2026-08-14", "POOR", "chopping above a few days' range, deep in downtrend"),
    ("BW",   "2026-08-11", "POOR", "below every MA; dead inside 60 seconds"),
    ("FRMI", "2026-08-11", "POOR", "below every MA; dead inside 60 seconds"),
]

# ── prod pulls (read-only SELECTs over ssh — the _stopgeom run_select shape) ───────────

ALERTS_SQL = """
SELECT DISTINCT ON (a.ticker, a.alert_date)
       a.ticker, a.alert_date, COALESCE(a.gap_pct, 0), COALESCE(a.ep_score, 0),
       COALESCE(a.score_tier, ''), COALESCE(a.judge_tier, ''),
       COALESCE(a.setup_class, ''), COALESCE(a.catalyst_quality, '')
FROM mi_ep_alerts a
ORDER BY a.ticker, a.alert_date, COALESCE(a.detected_at, a.created_at)
"""

DAILY_SQL = """
SELECT d.ticker, d.trade_date, d.open_price, d.high_price, d.low_price, d.close, d.volume
FROM mi_daily_closes d
WHERE d.ticker IN (SELECT DISTINCT ticker FROM mi_ep_alerts)
ORDER BY d.ticker, d.trade_date
"""

MINUTE_SQL = """
SELECT b.ticker, to_char(b.bar_time AT TIME ZONE 'America/New_York', 'YYYY-MM-DD HH24:MI'),
       b.open, b.high, b.low, b.close, b.volume
FROM (SELECT DISTINCT ticker, alert_date FROM mi_ep_alerts) a
JOIN mi_intraday_bars b
  ON b.ticker = a.ticker
 AND b.bar_time >= ((a.alert_date::text || ' 09:30')::timestamp AT TIME ZONE 'America/New_York')
 AND b.bar_time <  ((a.alert_date::text || ' 12:01')::timestamp AT TIME ZONE 'America/New_York')
ORDER BY b.ticker, b.bar_time
"""

SCORES_SQL = """
SELECT s.ticker, s.score_date, COALESCE(s.sma_10::text,''), COALESCE(s.sma_20::text,''),
       COALESCE(s.sma_50::text,''), COALESCE(s.rs_composite::text,''),
       COALESCE(s.rs_rank::text,''), COALESCE(s.close::text,'')
FROM mi_stock_scores s
WHERE s.ticker IN (SELECT DISTINCT ticker FROM mi_ep_alerts)
  AND s.score_date >= DATE '2026-08-07'
ORDER BY s.ticker, s.score_date
"""


def run_select(sql: str, timeout: int = 400) -> str:
    s = " ".join(sql.split())
    assert s.upper().startswith("SELECT"), "read-only: SELECTs only"
    assert not any(ch in s for ch in '"\\$`'), "unsupported char for ssh quoting"
    remote = f'docker exec -i apollo-postgres psql -U apollo -d apollo -tAX -c "{s}"'
    out = subprocess.run(["ssh", "-o", "ConnectTimeout=15", HOST, remote],
                         capture_output=True, text=True, timeout=timeout)
    if out.returncode != 0:
        raise RuntimeError(f"psql failed: {out.stderr.strip()[:500]}")
    return out.stdout


def pull() -> None:
    for sql, path, label in [(ALERTS_SQL, ALERTS_TSV, "alerts"),
                             (DAILY_SQL, DAILY_TSV, "daily"),
                             (MINUTE_SQL, MINUTE_TSV, "minute"),
                             (SCORES_SQL, SCORES_TSV, "scores")]:
        txt = run_select(sql)
        path.write_text(txt, encoding="utf-8")
        n = sum(1 for ln in txt.splitlines() if ln.strip())
        print(f"pulled {label}: rows={n} -> {path.name}")


# ── data loading ───────────────────────────────────────────────────────────────────────

def _f(x: str) -> float | None:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def load_daily() -> dict[str, list[tuple[str, float, float, float, float, float]]]:
    """ticker -> [(date, o, h, l, c, v)] sorted by date."""
    out: dict[str, list] = defaultdict(list)
    for ln in DAILY_TSV.read_text(encoding="utf-8").splitlines():
        p = ln.split("|")
        if len(p) != 7:
            continue
        t, d = p[0], p[1]
        o, h, l, c, v = (_f(x) for x in p[2:7])
        if None in (o, h, l, c) or c <= 0 or h <= 0:
            continue
        out[t].append((d, o, h, l, c, v or 0.0))
    for t in out:
        out[t].sort()
    return dict(out)


def load_minute() -> dict[tuple[str, str], list[tuple[str, float, float, float, float]]]:
    """(ticker, date) -> [(HH:MM, o, h, l, c)] sorted, 09:30-12:00 ET."""
    out: dict[tuple[str, str], list] = defaultdict(list)
    for ln in MINUTE_TSV.read_text(encoding="utf-8").splitlines():
        p = ln.split("|")
        if len(p) != 7:
            continue
        t, dt = p[0], p[1]
        d, hm = dt[:10], dt[11:16]
        o, h, l, c = (_f(x) for x in p[2:6])
        if None in (o, h, l, c):
            continue
        out[(t, d)].append((hm, o, h, l, c))
    for k in out:
        out[k].sort()
    return dict(out)


def load_alerts() -> list[dict]:
    rows = []
    for ln in ALERTS_TSV.read_text(encoding="utf-8").splitlines():
        p = ln.split("|")
        if len(p) != 8:
            continue
        rows.append({"ticker": p[0], "date": p[1], "gap_pct": _f(p[2]),
                     "ep_score": _f(p[3]), "tier": p[4], "judge": p[5],
                     "setup_class": p[6], "catalyst": p[7]})
    return rows


# ── the encoder core ───────────────────────────────────────────────────────────────────

def adr20_pct(days: list, ia: int) -> float | None:
    lo = max(0, ia - ADR_LOOKBACK)
    win = days[lo:ia]
    if len(win) < 10:
        return None
    return st.fmean((h - l) / c * 100.0 for _, _, h, l, c, _ in win)


def pivot_levels(days: list, ia: int, adr: float) -> list[dict]:
    """Merged pivot-high levels over days[:ia] with test-episode counting.

    Returns levels: {price, n_episodes, first_test, last_test, broken} — the lookback
    of each level IS its own test dates (derived, not fixed).
    """
    end = ia
    highs = [d[2] for d in days[:end]]
    piv_idx = []
    for i in range(PIVOT_WING, end - PIVOT_WING):
        left = max(highs[i - PIVOT_WING:i])
        right = max(highs[i + 1:i + 1 + PIVOT_WING])
        if highs[i] >= left and highs[i] > right:
            piv_idx.append(i)
    if not piv_idx:
        return []
    # merge pivot prices within MERGE_PCT into candidate levels (level = cluster max)
    piv_sorted = sorted(piv_idx, key=lambda i: highs[i])
    clusters: list[list[int]] = []
    for i in piv_sorted:
        if clusters and highs[i] <= max(highs[j] for j in clusters[-1]) * (1 + MERGE_PCT / 100.0):
            clusters[-1].append(i)
        else:
            clusters.append([i])
    levels = []
    for cl in clusters:
        L = max(highs[j] for j in cl)
        # break: last daily close above the level — tests only count after it
        last_break = -1
        for j in range(end):
            if days[j][4] > L * CLOSE_TOL:
                last_break = j
        prox = L * (1 - TEST_PROX_ADR * adr / 100.0)
        test_idx = [j for j in range(last_break + 1, end)
                    if days[j][2] >= prox and days[j][4] < L * CLOSE_TOL]
        if not test_idx:
            continue
        # group tests into EPISODES: a new episode only after a real rejection between
        reject_at = L * (1 - REJECT_ADR * adr / 100.0)
        episodes = 1
        prev = test_idx[0]
        ep_bounds = [test_idx[0]]
        for j in test_idx[1:]:
            between_low = min(days[k][3] for k in range(prev, j + 1))
            if between_low <= reject_at:
                episodes += 1
                ep_bounds.append(j)
            prev = j
        levels.append({"price": L, "n_episodes": episodes,
                       "first_test": days[test_idx[0]][0], "last_test": days[test_idx[-1]][0],
                       "kind": "pivot"})
    return levels


def sma50_level(days: list, ia: int, adr: float) -> dict | None:
    """The 50-day SMA as a level — ONLY if it acted as resistance (>=2 failed episodes
    in the current below-the-SMA regime) and is overhead at the alert."""
    if ia < 51:
        return None

    def sma(i: int) -> float:          # SMA50 through day i inclusive
        return st.fmean(days[j][4] for j in range(i - 49, i + 1))

    s_prior = sma(ia - 1)
    prior_close = days[ia - 1][4]
    if prior_close >= s_prior:
        return None                     # not overhead — price already above it
    # current below-regime: walk back while close < sma
    start = ia - 1
    while start - 1 >= 50 and days[start - 1][4] < sma(start - 1):
        start -= 1
    test_idx = []
    for j in range(start, ia):
        sj = sma(j)
        if days[j][2] >= sj * (1 - TEST_PROX_ADR * adr / 100.0) and days[j][4] < sj * CLOSE_TOL:
            test_idx.append(j)
    if not test_idx:
        return None
    episodes = 1
    prev = test_idx[0]
    for j in test_idx[1:]:
        between_low = min(days[k][3] for k in range(prev, j + 1))
        if between_low <= sma(j) * (1 - REJECT_ADR * adr / 100.0):
            episodes += 1
        prev = j
    if episodes < 2:
        return None
    return {"price": s_prior, "n_episodes": episodes,
            "first_test": days[test_idx[0]][0], "last_test": days[test_idx[-1]][0],
            "kind": "sma50"}


def five_min_closes(bars: list) -> list[tuple[str, float]]:
    """[(boundary HH:MM, close)] at 09:34, 09:39, ... from minute bars."""
    out = []
    if not bars:
        return out
    boundaries = []
    hh, mm = 9, 34
    while (hh, mm) <= (12, 0):
        boundaries.append(f"{hh:02d}:{mm:02d}")
        mm += 5
        if mm >= 60:
            hh, mm = hh + 1, mm - 60
    bi = 0
    last_close = None
    for b in boundaries:
        while bi < len(bars) and bars[bi][0] <= b:
            last_close = bars[bi][4]
            bi += 1
        if last_close is not None:
            out.append((b, last_close))
    return out


def encode(ticker: str, d: str, daily: dict, minute: dict, preopen: bool = False) -> dict:
    """The full structure encoding for one (ticker, alert_date).

    preopen=True suppresses ALL intraday information (no drive-breach, no hold, MA
    check against the open) — the verdict then uses only what was knowable at 09:30.
    """
    if preopen:
        minute = {}
    r: dict = {"ticker": ticker, "date": d, "flags": []}
    days = daily.get(ticker)
    if not days:
        r["error"] = "no_daily"
        return r
    idx = {row[0]: i for i, row in enumerate(days)}
    if d not in idx:
        r["error"] = "alert_day_not_in_daily"
        return r
    ia = idx[d]
    if ia < MIN_HISTORY:
        r["flags"].append(f"insufficient_history({ia}d)")
    if ia < 10:
        r["error"] = f"history_too_thin({ia}d)"
        return r
    adr = adr20_pct(days, ia)
    if adr is None or adr <= 0:
        r["error"] = "no_adr"
        return r
    open_px = days[ia][1]
    prior_close = days[ia - 1][4]
    prior_high = days[ia - 1][2]
    hist_max = max(days[j][2] for j in range(ia))
    r.update(history_days=ia, adr20_pct=round(adr, 2), open=open_px,
             prior_close=prior_close, hist_max=hist_max,
             gap_open_pct=round((open_px / prior_close - 1) * 100, 1))

    # 1 — levels (lookback derived from each level's own tests)
    levels = pivot_levels(days, ia, adr)
    s50 = sma50_level(days, ia, adr)
    if s50:
        levels.append(s50)
    qualified = [L for L in levels if L["n_episodes"] >= 2 or L["kind"] == "sma50"]
    overhead_q = [L for L in qualified if L["price"] > prior_close * 1.0]
    weak_overhead = [L for L in levels if L["n_episodes"] == 1 and L["kind"] == "pivot"
                     and L["price"] > prior_close]

    # 2 — did the gap clear it: open above, OR a 5-min close above in the opening drive
    bars = minute.get((ticker, d), [])
    scale_ok = True
    closes5: list[tuple[str, float]] = []
    if bars:
        if abs(bars[0][1] / open_px - 1) > 0.02:
            scale_ok = False
            r["flags"].append("scale_mismatch_minute_vs_daily")
        else:
            closes5 = five_min_closes(bars)
    else:
        r["flags"].append("no_minute_bars")
    r["first_5m_close"] = closes5[0][1] if closes5 else None

    def breached(price: float) -> bool:
        if open_px > price:
            return True
        if closes5:
            return any(c > price for b, c in closes5 if b <= BREACH_CUTOFF)
        return False   # degraded open-only (flagged via no_minute_bars / scale_mismatch)

    cleared_q = [L for L in overhead_q if breached(L["price"])]
    uncleared_q = [L for L in overhead_q if not breached(L["price"])]

    # 3 — held after the first pullback: END-STATE of the window vs the cleared level,
    # WITH MARGIN ("pulled back and HELD UP" tolerates a dip-and-reclaim; "drop and
    # HELD BELOW" = the window ends below; ending ON the level = onto, not through)
    def end_close(cutoff: str) -> float | None:
        window = [c for b, c in closes5 if b <= cutoff]
        return window[-1] if window else None

    ends = {"h60": end_close("10:30"), "h120": end_close("11:30"), "hmorn": end_close("12:00")}

    def held_margin(ref: float, cutoff_key: str, margin: bool = True) -> bool | None:
        e = ends[cutoff_key]
        if e is None:
            return None
        bar = ref * (1 + MARGIN_ADR * adr / 100.0) if margin else ref * HOLD_TOL
        return e >= bar

    def hold(ref: float, margin: bool = True) -> dict:
        return {k: held_margin(ref, k, margin) for k in ("h60", "h120", "hmorn")}

    # 5 — congestion above the open (c4/c5's remaining-overhead set is finished after
    # the class block, once we know which cleared levels were actually HELD)
    band_top = open_px * (1 + BAND_ADR * adr / 100.0)
    c1 = sum(1 for j in range(ia) if open_px < days[j][4] <= band_top)
    lo60 = max(0, ia - 60)
    c2 = sum(1 for j in range(lo60, ia) if open_px < days[j][4] <= band_top)
    c3 = 100.0 * sum(1 for j in range(lo60, ia) if days[j][4] > open_px) / max(1, ia - lo60)
    touch60 = sum(1 for j in range(lo60, ia) if days[j][2] >= open_px and days[j][3] <= band_top)
    r.update(band_top=round(band_top, 2), c1_full_band=c1, c2_60d_band=c2,
             c3_60d_above_pct=round(c3, 1), touch_60d_band=touch60)

    # 4 — classes (his failure classes are two of them).  KEY LEVEL = the highest
    # cleared level HELD WITH MARGIN at the primary window end (SE held its base top
    # +2.4 ADR while its opening spike poked and lost an old shelf — the poke is
    # congestion context, not the key level)
    key_level = None
    held = {"h60": None, "h120": None, "hmorn": None}
    if open_px > hist_max:
        klass = "BLUE_SKY"
        key_level = hist_max
        held = hold(key_level, margin=False)   # nothing overhead — no margin needed
        klass += {True: "_HELD", False: "_LOST", None: "_NOHOLDDATA"}[held["h60"]]
    elif cleared_q:
        if closes5:
            held_lv = [L["price"] for L in cleared_q if held_margin(L["price"], "h60")]
            if held_lv:
                key_level = max(held_lv)
                held = hold(key_level)
                klass = "CLEARED_HELD"
            else:
                key_level = max(L["price"] for L in cleared_q)
                held = hold(key_level)
                klass = "CLEARED_LOST"
        else:   # degraded (no minutes): open-margin decides, hold unknowable
            dec = [L["price"] for L in cleared_q
                   if open_px >= L["price"] * (1 + MARGIN_ADR * adr / 100.0)]
            key_level = max(dec) if dec else max(L["price"] for L in cleared_q)
            klass = "CLEARED_DECISIVE_NOHOLDDATA" if dec else "CLEARED_MARGINAL_NOHOLDDATA"
    elif uncleared_q:
        klass = "NEVER_BREACHED"
    elif hist_max <= band_top:
        klass = "NEAR_ATH"
        cw = [L["price"] for L in weak_overhead if breached(L["price"])]
        key_level = max(cw) if cw else (prior_high if open_px > prior_high else None)
        if key_level is not None:
            held = hold(key_level, margin=False)
            klass += {True: "_HELD", False: "_LOST", None: "_NOHOLDDATA"}[held["h60"]]
        else:
            klass += "_HELD" if closes5 else "_NOHOLDDATA"   # nothing to lose
    else:
        klass = "NO_LEVEL"

    # the overhead-MA check — "gapped up through the 50d which is A RESISTANCE" vs
    # landing ON it: every MA that sat ABOVE the prior close must end the window
    # MARGIN_ADR clear.  (SE was above all MAs pre-gap -> vacuously true.)
    def sma(n: int) -> float | None:
        return st.fmean(days[j][4] for j in range(ia - n, ia)) if ia >= n else None

    overhead_mas = {f"sma{n}": v for n in (10, 20, 50)
                    if (v := sma(n)) is not None and v > prior_close}
    e60 = ends["h60"]
    ref_px = e60 if e60 is not None else open_px
    ma_cleared = all(ref_px >= v * (1 + MARGIN_ADR * adr / 100.0)
                     for v in overhead_mas.values()) if overhead_mas else True
    r.update(overhead_mas={k: round(v, 2) for k, v in overhead_mas.items()},
             ma_cleared=ma_cleared, end_10_30=e60)
    r.update(cls=klass, key_level=(round(key_level, 2) if key_level else None),
             n_levels_all=len(levels), n_qualified_overhead=len(overhead_q),
             n_cleared=len(cleared_q), n_uncleared=len(uncleared_q),
             held_60=held["h60"], held_120=held["h120"], held_morning=held["hmorn"],
             levels_detail=[{"price": round(L["price"], 2), "kind": L["kind"],
                             "episodes": L["n_episodes"], "first_test": L["first_test"],
                             "last_test": L["last_test"],
                             "cleared": breached(L["price"]) if L["price"] > prior_close else None,
                             "held": (held_margin(L["price"], "h60")
                                      if (L["price"] > prior_close and breached(L["price"])
                                          and closes5) else None)}
                            for L in sorted(qualified, key=lambda x: x["price"])])

    # remaining overhead = never breached, plus breached-but-not-held-with-margin
    remaining = [L for L in uncleared_q]
    if closes5:
        remaining += [L for L in cleared_q if not held_margin(L["price"], "h60")]
    c4 = sum(1 for L in remaining if L["price"] <= band_top)
    c5 = min(((L["price"] / open_px - 1) * 100 / adr for L in remaining), default=None)
    r.update(c4_overhead_in_band=c4,
             c5_adr_to_next_level=(round(c5, 2) if c5 is not None else None))

    # verdict — cleared real overhead (or had none) + held the window end with margin +
    # took out every overhead MA + not buried under its own recent history
    deep_in_downtrend = c3 >= MAX_C3_PCT
    if preopen:
        good_class = klass in ("BLUE_SKY_NOHOLDDATA", "CLEARED_DECISIVE_NOHOLDDATA",
                               "NEAR_ATH_NOHOLDDATA")
    else:
        good_class = klass in ("BLUE_SKY_HELD", "CLEARED_HELD", "NEAR_ATH_HELD",
                               "CLEARED_DECISIVE_NOHOLDDATA")   # last = degraded Tier-B
    r["deep_in_downtrend_veto"] = deep_in_downtrend
    r["verdict"] = "GOOD" if (good_class and not deep_in_downtrend and ma_cleared) else "POOR"
    return r


# ── fixtures (the gate) ────────────────────────────────────────────────────────────────

def run_fixtures() -> None:
    daily, minute = load_daily(), load_minute()
    print("=" * 96)
    print("NBIS STRUCTURE ENCODER — FIXTURE GATE (8 operator-labelled reads; the encoder")
    print("must reproduce them BEFORE any population sweep — else STOP, per the plan)")
    print("=" * 96)
    print("Definition encoded: docs/roadmap/ep_profitability_program.md §2 THE NBIS ENCODING.")
    print("Level lookback is DERIVED from each level's own failed-test dates (no fixed window).")
    print(f"Params (all from his shared sources): merge {MERGE_PCT}% (RMVP) · test proximity "
          f"{TEST_PROX_ADR}xADR20 · episode separation {REJECT_ADR}xADR20 rejection · "
          f"congestion band {BAND_ADR}xADR20 (RMVP multiplier) · hold window 60 min primary.")
    print(f"The three fixture-calibrated numbers (disclosed): breach window = opening drive "
          f"through {BREACH_CUTOFF} · deep-in-downtrend veto at >= {MAX_C3_PCT}% of last-60d "
          f"closes above the open · through-not-onto margin {MARGIN_ADR}xADR20 (hold end-state "
          f"and overhead-MA clearance). Hold = END-STATE of the window (dip-and-reclaim is a hold).\n")
    agree = 0
    results = []
    for tkr, d, label, words in FIXTURES:
        r = encode(tkr, d, daily, minute)
        results.append((tkr, d, label, words, r))
        if r.get("error"):
            print(f"{tkr:>5} {d}  ERROR: {r['error']}")
            continue
        ok = r["verdict"] == label
        agree += ok
        mark = "AGREE" if ok else "*** DISAGREE ***"
        print(f"{tkr:>5} {d}  his: {label:<4}  encoder: {r['verdict']:<4}  {mark}")
        print(f"      class={r['cls']}  key_level={r['key_level']}  gap_open={r['gap_open_pct']}%"
              f"  open={r['open']}  ADR20={r['adr20_pct']}%  history={r['history_days']}d")
        print(f"      levels: qualified_overhead={r['n_qualified_overhead']} "
              f"cleared={r['n_cleared']} uncleared={r['n_uncleared']}"
              f"  held60/120/morn={r['held_60']}/{r['held_120']}/{r['held_morning']}"
              f"  end_10:30={r['end_10_30']}")
        print(f"      MA check: overhead_mas={r['overhead_mas']}  ma_cleared={r['ma_cleared']}")
        print(f"      congestion: band_top={r['band_top']}  in-band closes 60d={r['c2_60d_band']} "
              f"(full={r['c1_full_band']})  %60d-closes-above-open={r['c3_60d_above_pct']}%  "
              f"remaining-overhead-in-band={r['c4_overhead_in_band']}  "
              f"ADR-to-next-level={r['c5_adr_to_next_level']}  "
              f"deep-in-downtrend-veto={r['deep_in_downtrend_veto']}")
        for L in r["levels_detail"]:
            print(f"        level {L['price']:>9} [{L['kind']}] episodes={L['episodes']} "
                  f"tests {L['first_test']}..{L['last_test']} cleared={L['cleared']} held={L['held']}")
        if r["flags"]:
            print(f"      flags: {', '.join(r['flags'])}")
        print(f"      his words: {words}")
        print()
    n = len(FIXTURES)
    passed = agree == n
    print("-" * 96)
    print(f"FIXTURE GATE: {agree}/{n} agree -> {'PASS' if passed else 'FAIL — STOP. No sweep, no distribution.'}")
    GATE_JSON.write_text(json.dumps({"agree": agree, "n": n, "passed": passed,
                                     "results": [{k: v for k, v in r.items() if k != 'levels_detail'}
                                                 for *_ , r in results]}, indent=1, default=str),
                         encoding="utf-8")
    print(f"(gate result -> {GATE_JSON.name})")


# ── population sweep (refuses to run unless the gate passed) ───────────────────────────

def perm_p(a: list[float], b: list[float], sess_a: list[str], sess_b: list[str]) -> float | None:
    """Median-difference permutation shuffling whole SESSIONS (house convention)."""
    by_sess: dict[str, list[float]] = defaultdict(list)
    for v, s in zip(a, sess_a):
        by_sess[s].append(v)
    for v, s in zip(b, sess_b):
        by_sess[s].append(v)
    sessions = sorted(by_sess)
    if len(a) < 5 or len(b) < 5 or len(sessions) < 6:
        return None
    obs = st.median(a) - st.median(b)
    rng = random.Random(RANDOM_SEED)
    counts = [len(by_sess[s]) for s in sessions]
    pool = [by_sess[s] for s in sessions]
    n_a = len(a)
    hits = 0
    for _ in range(N_PERM):
        idx = list(range(len(sessions)))
        rng.shuffle(idx)
        take, got = set(), 0
        for i in idx:
            if got >= n_a:
                break
            take.add(i)
            got += counts[i]
        pa = [v for i in take for v in pool[i]]
        pb = [v for i in range(len(sessions)) if i not in take for v in pool[i]]
        if not pa or not pb:
            continue
        if abs(st.median(pa) - st.median(pb)) >= abs(obs):
            hits += 1
    return (hits + 1) / (N_PERM + 1)


def fwd_outcomes(days: list, ia: int) -> dict:
    """Forward returns from the alert-day OPEN (the plan's open_d0 basis), % units."""
    o = days[ia][1]
    out = {}
    out["ret_1d"] = (days[ia + 1][4] / o - 1) * 100 if ia + 1 < len(days) else None
    out["ret_5d"] = (days[ia + 5][4] / o - 1) * 100 if ia + 5 < len(days) else None
    if ia + 5 < len(days):
        out["mfe_5d"] = (max(days[j][2] for j in range(ia, ia + 6)) / o - 1) * 100
    else:
        out["mfe_5d"] = None
    return out


def describe(vals: list[float]) -> str:
    if not vals:
        return "n=0"
    sv = sorted(vals)
    return (f"n={len(vals)} med={st.median(vals):+.2f}% mean={st.fmean(vals):+.2f}% "
            f"p25={sv[len(sv)//4]:+.2f}% p75={sv[3*len(sv)//4]:+.2f}% "
            f"up={100*sum(1 for v in vals if v>0)/len(vals):.0f}%")


def run_sweep() -> None:
    if not GATE_JSON.exists():
        sys.exit("REFUSED: run --fixtures first (gate result missing)")
    gate = json.loads(GATE_JSON.read_text(encoding="utf-8"))
    if not gate.get("passed"):
        sys.exit(f"REFUSED: fixture gate FAILED ({gate.get('agree')}/{gate.get('n')}) — "
                 "the plan forbids sweeping an encoding the operator would reject")
    daily, minute = load_daily(), load_minute()
    alerts = load_alerts()
    data_max = max(max(d[0] for d in v) for v in daily.values())
    print("=" * 96)
    print("POPULATION SWEEP — every mi_ep_alerts row, encoded; forward outcomes from the")
    print(f"alert-day OPEN, computed locally from mi_daily_closes (through {data_max}).")
    print("Gate passed upstream:", f"{gate['agree']}/{gate['n']} fixtures agree.")
    print("=" * 96)
    enc_rows = []
    funnel = defaultdict(int)
    for a in alerts:
        r = encode(a["ticker"], a["date"], daily, minute)
        funnel["alerts_total"] += 1
        if r.get("error"):
            funnel[f"drop:{r['error'].split('(')[0]}"] += 1
            continue
        days = daily[a["ticker"]]
        ia = next(i for i, row in enumerate(days) if row[0] == a["date"])
        r.update(fwd_outcomes(days, ia))
        r["tier"] = a["tier"]
        r["gap_pct"] = a["gap_pct"]
        enc_rows.append(r)
        funnel["encoded"] += 1
        if "no_minute_bars" in r["flags"] or "scale_mismatch_minute_vs_daily" in r["flags"]:
            funnel["tierB_daily_only"] += 1
        else:
            funnel["tierA_full"] += 1
    print("\nFUNNEL: " + " · ".join(f"{k}={v}" for k, v in sorted(funnel.items())))

    # class distribution
    print("\nCLASS DISTRIBUTION (all encoded alerts):")
    byc = defaultdict(list)
    for r in enc_rows:
        byc[r["cls"]].append(r)
    for k in sorted(byc, key=lambda k: -len(byc[k])):
        rows = byc[k]
        sess = len({r["date"] for r in rows})
        good = sum(1 for r in rows if r["verdict"] == "GOOD")
        print(f"  {k:<22} n={len(rows):>3}  sessions={sess:>2}  verdict-GOOD={good}")
    gv = [r for r in enc_rows if r["verdict"] == "GOOD"]
    pv = [r for r in enc_rows if r["verdict"] == "POOR"]
    print(f"\nVERDICT: GOOD={len(gv)} ({len({r['date'] for r in gv})} sessions) · "
          f"POOR={len(pv)} ({len({r['date'] for r in pv})} sessions)")

    # PRIMARY test — GOOD vs POOR on ret_5d, settled only, session-permuted
    print("\n" + "-" * 96)
    print("PRIMARY (pre-registered): GOOD vs POOR on ret_5d from alert-day open, settled")
    print("alerts only, permutation on SESSIONS. Secondaries are descriptive (Bonferroni x4).")
    for h in ["ret_5d", "mfe_5d", "ret_1d"]:
        g = [(r[h], r["date"]) for r in gv if r[h] is not None]
        p = [(r[h], r["date"]) for r in pv if r[h] is not None]
        gvv, gss = [x for x, _ in g], [s for _, s in g]
        pvv, pss = [x for x, _ in p], [s for _, s in p]
        pval = perm_p(gvv, pvv, gss, pss)
        tag = "PRIMARY" if h == "ret_5d" else "secondary"
        print(f"\n  [{tag}] {h}")
        print(f"    GOOD  {describe(gvv)}  sessions={len(set(gss))}")
        print(f"    POOR  {describe(pvv)}  sessions={len(set(pss))}")
        print(f"    session-permutation p={'N too small' if pval is None else f'{pval:.4f}'}")

    # gap-size control — is the verdict gap size in disguise?
    print("\n  [control] gap size by verdict (is GOOD just small-gap?):")
    for lbl, rows in [("GOOD", gv), ("POOR", pv)]:
        gaps = [r["gap_pct"] for r in rows if r["gap_pct"] is not None]
        if gaps:
            print(f"    {lbl}: median gap {st.median(gaps):.1f}%  (n={len(gaps)})")

    # Tier-A (full encoding incl. hold) subset
    print("\n  [secondary] Tier-A full-encoding subset (minutes present, scale-ok):")
    ta = [r for r in enc_rows if "no_minute_bars" not in r["flags"]
          and "scale_mismatch_minute_vs_daily" not in r["flags"]]
    for lbl, rows in [("GOOD", [r for r in ta if r["verdict"] == "GOOD"]),
                      ("POOR", [r for r in ta if r["verdict"] == "POOR"])]:
        vals = [r["ret_5d"] for r in rows if r["ret_5d"] is not None]
        print(f"    {lbl}: {describe(vals)}  sessions={len({r['date'] for r in rows if r['ret_5d'] is not None})}")
    # ⚠ CONTAMINATION NOTE + the uncontaminated read (post-hoc, labelled as such):
    # the full verdict's HOLD leg conditions on post-open action (a CLEARED_LOST name
    # mechanically embeds a bad morning), so open-basis forward returns partly RESTATE
    # the verdict at short horizons.  The pre-open-only verdict below uses NOTHING after
    # 09:30 (no drive-breach, no hold; MA margin vs the open) — it answers "does
    # structure knowable at the open predict", which is the selection question.
    print("\n" + "-" * 96)
    print("PRE-OPEN-ONLY VERDICT (POST-HOC, declared after the primary was read; not part")
    print("of the pre-registered battery). No intraday information at all: open-margin")
    print("clear + overhead-MA margin at the open + the downtrend veto. This removes the")
    print("hold leg's mechanical contamination of open-basis forward returns.")
    pre_rows = []
    for a in alerts:
        r = encode(a["ticker"], a["date"], daily, minute, preopen=True)
        if r.get("error"):
            continue
        days = daily[a["ticker"]]
        ia = next(i for i, row in enumerate(days) if row[0] == a["date"])
        r.update(fwd_outcomes(days, ia))
        pre_rows.append(r)
    pg = [r for r in pre_rows if r["verdict"] == "GOOD"]
    pp = [r for r in pre_rows if r["verdict"] == "POOR"]
    print(f"  split: GOOD={len(pg)} ({len({r['date'] for r in pg})} sessions) · "
          f"POOR={len(pp)} ({len({r['date'] for r in pp})} sessions)")
    for h in ["ret_5d", "mfe_5d", "ret_1d"]:
        g = [(r[h], r["date"]) for r in pg if r[h] is not None]
        p = [(r[h], r["date"]) for r in pp if r[h] is not None]
        gvv, gss = [x for x, _ in g], [s for _, s in g]
        pvv, pss = [x for x, _ in p], [s for _, s in p]
        pval = perm_p(gvv, pvv, gss, pss)
        print(f"\n  {h}")
        print(f"    GOOD  {describe(gvv)}  sessions={len(set(gss))}")
        print(f"    POOR  {describe(pvv)}  sessions={len(set(pss))}")
        print(f"    session-permutation p={'N too small' if pval is None else f'{pval:.4f}'}")

    print("\nHOW TO READ: the permutation p shuffles SESSIONS (same-morning alerts share the")
    print("tape). p above ~0.1 at these N means chance covers the difference. The full")
    print("verdict's short-horizon reads are partly mechanical (see contamination note);")
    print("the pre-open split is the honest selection read. Nothing here changes any grade,")
    print("gate, or entry — promotion is fork S-3 (THE LINE).")


if __name__ == "__main__":
    import os
    if os.environ.get("APOLLO_PROBE_WRITE"):
        sys.exit("this probe is read-only by design")
    if "--pull" in sys.argv:
        pull()
    elif "--fixtures" in sys.argv:
        run_fixtures()
    elif "--sweep" in sys.argv:
        run_sweep()
    else:
        print(__doc__)
