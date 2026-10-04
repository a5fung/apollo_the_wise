"""#394 C1 — the coil-finder tune probe (Family A detector; ADR 0013).

Spec: docs/analysis/394_coil_tuning_methodology_2026-07-11.md §1-§4 (methodology SIGNED 2026-07-12).
Prints, per population, the method's three tables and one mechanical verdict line per knob:
  3a HOLD CAP sweep {40%, 50%, 60%}  ·  3b RANK ORDERING Spearman vs settled R  ·  3c ORDERLINESS quartiles.
The coil-finder is a DETECTOR; its board states (coiled / post_runup / aged) are states, not setups.
This probe DECIDES NOTHING LIVE: C2 applies verdicts only with the operator's signed tables.

Run (ONE capture, never re-run to re-read):
    ssh apollo@87.99.134.162 "docker exec -i apollo-market python -" \
        < scripts/probes/_394_coil_tune.py > scripts/probes/_394/coil_tune_out_<YYYY-MM-DD>.txt 2>&1
(the 2026-10-03 capture is scripts/probes/_394/coil_tune_out_2026-10-03.txt; the C3 re-run — data-gated
review `coil_tune_rerun_394` — must run AFTER the C2 deploy, since it imports anticipation.orderliness_score)
Selftest (local, no DB):
    python scripts/probes/_394_coil_tune.py --selftest

READ-ONLY: every query is a SELECT inside a READ ONLY transaction (the server rejects any write).
No model calls, no writes, no orders.

LIVE-CODE FIDELITY — the probe IMPORTS (does not mirror) the live primitives, so it measures exactly
what the running container computes; the run prints the module identity (file, COIL_HOLD_LIMIT, a
hash of find_coil_setup's source) so the reader can tell which build ran:
  hold retrace  ← anticipation.find_coil_setup(bars[:i+1], i)["retrace"]  (the quantity COIL_HOLD_LIMIT
                  gates in evaluate_coil_consolidation: (peak − min low after the peak) / runup leg)
  board keys    ← anticipation.tight_close_streak, anticipation.compute_rmv(lookback=15), and
                  today_pct = |c/c_prev − 1| (inline in evaluate_coil_consolidation; mirrored below)
  ATR14         ← flag_detector._atr_14 on anticipation.bars_to_rmv_rows (same as atr14_pct on the board)
  orderliness   ← anticipation.orderliness_score (+ percentile / overnight_gap_pcts / atr14_pct /
                  MIN_GAP_DAYS) — the method's §3c metric. It was DEFINED in this probe for C1 and, at
                  C2 (2026-10-03, operator "Sign" — display only), MOVED VERBATIM into the live module so
                  the board's stored score and this probe's tables are one definition, not two that can
                  drift. The probe imports it; tests/test_394_coil_tune_probe.py pins the identity.
(find_coil_setup's `adr` field is commented ORDERLINESS but is the mean intraday range the operator
rejected for this purpose — PLAN #394: "overnight-gap / max-daily-move, NOT the intraday-ADR" — so it
is not used here.)

INTERPRETATIONS (the method leaves these open; each is a named constant below):
  * cohort = origin 'family_a', settled (outcome AND realized_r non-NULL), entry_date ≥ CORRECTED_BASE_FROM
    (commit c26b3add made the coil-finder the live base on Sat 2026-06-27; first mon-fri scan 06-29).
    The method's "settled R" = realized_r (the column /anticipation's edge header reports) — the legacy
    5-day harvest horizon (settle_entry_shadow); realized_r_h12 (12-bar) is NOT what the verdicts rest on.
  * (ii) "RMV-tightness-led" sorts on rmv_15d (the #327 gate's canonical baseline since 2026-06-27), not
    the rmv_5d the /anticipation board row displays.
  * 3a decisive N = the rows in the MARGINAL band between the incumbent cap and the proposed cap (the
    rows whose admission actually changes), not the proposed cell's size.
  * 3b/3c keys are read AS OF the bar BEFORE the entry bar (ORDERING_ASOF_OFFSET) — the last board the
    operator saw before the fire. On a Confirm row the entry bar IS the breakout (streak 0, big move)
    so keys read there carry no ordering information.
  * 3c base window = bars (anchor, entry) exclusive: the post-peak consolidation before the entry bar.
    Days with a NULL open are DROPPED from the P95 (db_rows_to_bars substitutes the close for a NULL
    open and flags `o_missing`; reading the substitute would turn an overnight gap into a
    close-to-close move).
  * (iv) = the incumbent board order with the top orderliness quartile (gappiest) demoted beneath all
    others; one rank-based quartile_index serves both 3b(iv) and the 3c table.
"""
from __future__ import annotations

import hashlib
import inspect
import os
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta

_FILE = globals().get("__file__")
if _FILE and os.path.exists(_FILE):          # local run: make `agents` importable; piped run has no __file__
    _ROOT = os.path.abspath(os.path.join(os.path.dirname(_FILE), "..", ".."))
    if _ROOT not in sys.path:
        sys.path.insert(0, _ROOT)

from agents.market_intelligence.anticipation import (   # noqa: E402 — LIVE primitives, imported not mirrored
    COIL_HOLD_LIMIT, compute_rmv, db_rows_to_bars, find_coil_setup, orderliness_score, percentile,
    tight_close_streak,
)

# ── method constants (§2/§3) ─────────────────────────────────────────────────────────────────────
HOLD_CAPS = (0.40, 0.50, 0.60)
INCUMBENT_CAP = 0.50            # asserted == live COIL_HOLD_LIMIT at run time
RECALL_GUARD = 0.30             # 3a: a cap may not cut the admitted count by more than 30%
ADOPT_GAP = 0.15                # 3b: a challenger must beat the incumbent's Spearman by >= 0.15
DEMOTE_GAP_R = 0.5              # 3c: top quartile underperforms the rest by >= 0.5R median
MIN_DECISIVE_N = 10             # §2 per-knob honesty: decisive cell N < 10 -> unchanged
MIN_PRIMARY_N = 20              # §2 primary gate (3b reads "at N>=20")

# ── interpretation constants (see module docstring) ──────────────────────────────────────────────
CORRECTED_BASE_FROM = date(2026, 6, 29)
ORDERING_ASOF_OFFSET = 1
BAR_LOOKBACK_DAYS = 200         # calendar days of bars before the earliest entry (coil-finder reads <= 80 bars)
R_COL = "realized_r"

POPULATIONS = (                 # (label, entry_mode, stop_kind); POOLED is appended in main()
    ("confirm/base_low", "confirm", "base_low"),
    ("anticipate/coiled_low", "anticipate", "coiled_low"),
    ("anticipate/structural_low", "anticipate", "structural_low"),
)
POOLED = "POOLED family_a (all modes)"

ORDERINGS = ("(i) incumbent", "(ii) rmv-led", "(iii) streak-led", "(iv) orderliness-demoted")


# ═════════════════════════════════════════════════════════════════════════════════════════════════
# Pure helpers
# ═════════════════════════════════════════════════════════════════════════════════════════════════
def median(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def win_rate(xs):
    xs = [x for x in xs if x is not None]
    return (sum(1 for x in xs if x > 0) / len(xs)) if xs else None


def today_pct(bars, i):
    """|close % change| at bar i — mirrors evaluate_coil_consolidation's inline `today_pct`."""
    if i < 1 or not bars[i - 1]["c"]:
        return None
    return round(abs(bars[i]["c"] / bars[i - 1]["c"] - 1), 5)


def hold_retrace(bars, i):
    """(retrace, peak_date) of the LIVE coil-finder at bar i, point-in-time (bars[:i+1]); (None, None)
    when find_coil_setup finds no runup->consolidation at i."""
    s = find_coil_setup(bars[:i + 1], i)
    if s is None:
        return None, None
    return s["retrace"], s["peak_date"]


def avg_ranks(xs):
    """1-based average ranks (ties share the mean rank). xs must be mutually comparable."""
    order = sorted(range(len(xs)), key=lambda k: xs[k])
    ranks = [0.0] * len(xs)
    j = 0
    while j < len(order):
        k = j
        while k + 1 < len(order) and xs[order[k + 1]] == xs[order[j]]:
            k += 1
        r = (j + k) / 2.0 + 1.0
        for m in range(j, k + 1):
            ranks[order[m]] = r
        j = k + 1
    return ranks


def spearman(x, y):
    """Spearman rho = Pearson on average ranks. None when n < 3 or either side is constant."""
    if len(x) != len(y) or len(x) < 3:
        return None
    rx, ry = avg_ranks(x), avg_ranks(y)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    sxy = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    sxx = sum((a - mx) ** 2 for a in rx)
    syy = sum((b - my) ** 2 for b in ry)
    if sxx == 0 or syy == 0:
        return None
    return sxy / (sxx * syy) ** 0.5


def quartile_index(values):
    """Rank-based quartile 0..3 per element (3 = highest values). None stays None. Ties are broken by
    input order (deterministic). ONE function feeds both the 3c table and the (iv) demotion flag."""
    idx = [k for k, v in enumerate(values) if v is not None]
    idx.sort(key=lambda k: (values[k], k))
    n = len(idx)
    out = [None] * len(values)
    for rank, k in enumerate(idx):
        out[k] = min(3, (4 * rank) // n)
    return out


# ── 3a ────────────────────────────────────────────────────────────────────────────────────────────
def hold_cap_cells(items, caps=HOLD_CAPS):
    """items: [(retrace, r)] with retrace not None. -> [{cap, n, median_r, win_rate}]"""
    cells = []
    for c in caps:
        rs = [r for t, r in items if t <= c + 1e-12]
        cells.append({"cap": c, "n": len(rs), "median_r": median(rs), "win_rate": win_rate(rs)})
    return cells


def _sign(x):
    return 0 if x is None or x == 0 else (1 if x > 0 else -1)


def hold_cap_verdict(cells, items, incumbent=INCUMBENT_CAP, *, recall_guard=RECALL_GUARD,
                     min_n=MIN_DECISIVE_N):
    """The §3a rule, mechanical. Returns (code, text). Codes: KEEP | MOVE <cap> | KNIFE-EDGE | INSUFFICIENT.
    Knife-edge = adjacent cells' median R of strictly opposite sign. Eligible = admitted count ≥
    (1 − recall_guard) × the incumbent's. Proposal = eligible cell with the highest median R (ties
    keep the incumbent). The decisive N is the MARGINAL band between incumbent and proposal."""
    by_cap = {c["cap"]: c for c in cells}
    inc = by_cap[incumbent]
    if inc["n"] < min_n:
        return "INSUFFICIENT", f"incumbent cell N={inc['n']} < {min_n} -> unchanged"
    for a, b in zip(cells, cells[1:]):
        if _sign(a["median_r"]) * _sign(b["median_r"]) < 0:
            return "KNIFE-EDGE", (f"adjacent cells {a['cap']:.0%}/{b['cap']:.0%} disagree in sign "
                                  f"({a['median_r']:+.2f}R vs {b['median_r']:+.2f}R) -> no change, re-arm")
    floor = (1 - recall_guard) * inc["n"]
    eligible = [c for c in cells if c["n"] >= floor and c["median_r"] is not None]
    best = inc
    for c in eligible:
        if c["median_r"] > best["median_r"] + 1e-12 or (
                abs(c["median_r"] - best["median_r"]) <= 1e-12 and c["cap"] == incumbent):
            best = c
    if best["cap"] == incumbent:
        return "KEEP", f"keep {incumbent:.0%} (no eligible cell beats its median {inc['median_r']:+.2f}R)"
    lo, hi = sorted((incumbent, best["cap"]))
    band = sum(1 for t, _ in items if lo + 1e-12 < t <= hi + 1e-12)
    if band < min_n or best["n"] < min_n:
        return "INSUFFICIENT", (f"best cell {best['cap']:.0%} ({best['median_r']:+.2f}R) rests on "
                                f"{band} rows in ({lo:.0%},{hi:.0%}] < {min_n} -> unchanged")
    return f"MOVE {best['cap']:.0%}", (f"move {incumbent:.0%} -> {best['cap']:.0%} (median {inc['median_r']:+.2f}R -> "
                    f"{best['median_r']:+.2f}R; admitted {inc['n']} -> {best['n']}; band N={band})")


# ── 3b ────────────────────────────────────────────────────────────────────────────────────────────
_INF = float("inf")


def ordering_keys(row, gappy):
    """Board sort keys for one candidate, ASCENDING = higher on the board. `gappy` = in the top
    orderliness quartile. NULLs sort last, matching the live ORDER BY ... NULLS LAST."""
    streak = row.get("streak")
    tp = row.get("today_pct")
    rmv = row.get("rmv_15d")
    s_key = -streak if streak is not None else _INF
    t_key = tp if tp is not None else _INF
    r_key = rmv if rmv is not None else _INF
    return {
        "(i) incumbent": (s_key, t_key),                  # live: tight_close_streak DESC, today_pct ASC
        "(ii) rmv-led": (r_key, t_key),                   # rmv_15d ASC (lower = more contracted)
        "(iii) streak-led": (s_key,),                     # tight_close_streak DESC alone
        "(iv) orderliness-demoted": (1 if gappy else 0, s_key, t_key),
    }


def board_scores(keys):
    """Sort keys (ascending = better) -> a score where HIGHER = higher on the board."""
    return [-r for r in avg_ranks(keys)]


def ordering_verdict(rhos, n, *, gap=ADOPT_GAP, min_n=MIN_PRIMARY_N):
    """§3b: adopt the best challenger only if rho beats the incumbent's by >= gap at N >= min_n."""
    inc = rhos.get("(i) incumbent")
    if n < min_n:
        return "INSUFFICIENT", f"N={n} < {min_n} -> unchanged"
    if inc is None:
        return "INSUFFICIENT", "incumbent Spearman undefined (constant ordering or R) -> unchanged"
    challengers = [(k, v) for k, v in rhos.items() if k != "(i) incumbent" and v is not None]
    if not challengers:
        return "KEEP", "no challenger has a defined Spearman"
    best_k, best_v = max(challengers, key=lambda kv: kv[1])
    if best_v - inc >= gap - 1e-12:
        return f"ADOPT {best_k.split()[0]}", f"adopt {best_k} (rho {best_v:+.3f} vs incumbent {inc:+.3f}, gap {best_v - inc:+.3f})"
    return "KEEP", (f"keep incumbent (best challenger {best_k} rho {best_v:+.3f} vs {inc:+.3f}, "
                    f"gap {best_v - inc:+.3f} < {gap})")


# ── 3c ────────────────────────────────────────────────────────────────────────────────────────────
def quartile_table(scores, rs):
    """-> [{q, n, lo, hi, median_r, win_rate}] for quartiles 1..4 (4 = gappiest) + the q-index list."""
    qi = quartile_index(scores)
    rows = []
    for q in range(4):
        sel = [k for k, v in enumerate(qi) if v == q]
        sc = [scores[k] for k in sel]
        rr = [rs[k] for k in sel]
        rows.append({"q": q + 1, "n": len(sel), "lo": min(sc) if sc else None,
                     "hi": max(sc) if sc else None, "median_r": median(rr), "win_rate": win_rate(rr)})
    return rows, qi


def demotion_verdict(top_rs, rest_rs, *, gap=DEMOTE_GAP_R, min_n=MIN_DECISIVE_N):
    """§3c Phase 2: DEMOTE iff the top (gappiest) quartile's median R trails the rest's by >= gap,
    with >= min_n on each side. Never a hard gate — demotion = ordering (iv)."""
    if len(top_rs) < min_n or len(rest_rs) < min_n:
        return "INSUFFICIENT", f"top N={len(top_rs)}, rest N={len(rest_rs)} (need {min_n} each) -> unchanged"
    mt, mr = median(top_rs), median(rest_rs)
    if mr - mt >= gap - 1e-12:
        return "DEMOTE", (f"gappiest quartile median {mt:+.2f}R trails the rest {mr:+.2f}R by "
                          f"{mr - mt:.2f}R >= {gap} -> orderliness joins the ranking as ordering (iv)")
    return "NO-DEMOTE", (f"gappiest quartile median {mt:+.2f}R vs rest {mr:+.2f}R (gap {mr - mt:+.2f}R "
                         f"< {gap}) -> display only (Phase 1)")


# ── combining ─────────────────────────────────────────────────────────────────────────────────────
_NO_CHANGE = ("KEEP", "KNIFE-EDGE", "NO-DEMOTE")


def action_of(code):
    """A verdict code -> what it does to the live knob: 'NO CHANGE', 'UNCHANGED' (insufficient), or
    the change itself ('MOVE 40%', 'ADOPT (ii)', 'DEMOTE')."""
    if code == "INSUFFICIENT":
        return "UNCHANGED"
    return "NO CHANGE" if code in _NO_CHANGE else code


def combine_verdicts(per_pop):
    """{pop: (code, text)} -> the knob's final (action, text). INSUFFICIENT populations do not vote;
    voters compared on their ACTION (KEEP / KNIFE-EDGE / NO-DEMOTE all mean no change); all agree ->
    that action; disagree -> SPLIT (operator ruling); no voters -> UNCHANGED."""
    votes = {p: c for p, (c, _) in per_pop.items() if c != "INSUFFICIENT"}
    abstain = sorted(p for p, (c, _) in per_pop.items() if c == "INSUFFICIENT")
    if not votes:
        return "UNCHANGED", "every population INSUFFICIENT -> unchanged, re-arm"
    actions = {p: action_of(c) for p, c in votes.items()}
    tail = f" · not voting (N below the gate): {', '.join(abstain)}" if abstain else ""
    knife = sorted(p for p, c in votes.items() if c == "KNIFE-EDGE")
    if knife:
        tail += f" · knife-edge in {', '.join(knife)} -> re-arm"
    if len(set(actions.values())) == 1:
        return next(iter(actions.values())), "voting: " + ", ".join(sorted(votes)) + tail
    return "SPLIT", ("populations disagree -> operator ruling: "
                     + "; ".join(f"{p}={c}" for p, c in sorted(votes.items())) + tail)


def fmt(x, spec="+.2f", none="  –"):
    return none if x is None else format(x, spec)


# ═════════════════════════════════════════════════════════════════════════════════════════════════
# Per-row measurement (pure on bars)
# ═════════════════════════════════════════════════════════════════════════════════════════════════
rows_to_bars = db_rows_to_bars   # the live converter now flags a NULL open itself (`o_missing`) — one converter


def bars_by_ticker(bar_rows):
    """{ticker: bars} + {ticker: error} — one unreadable row (NULL high/low) drops ITS ticker, counted,
    instead of aborting the only capture."""
    raw_by = defaultdict(list)
    for r in bar_rows:
        raw_by[r["ticker"]].append(r)
    good, bad = {}, {}
    for t, rs in raw_by.items():
        try:
            good[t] = rows_to_bars(rs)
        except (TypeError, ValueError, KeyError) as e:
            bad[t] = e.__class__.__name__
    return good, bad


def measure_row(row, bars):
    """Everything the three tables need for one shadow row. Never raises — a short/missing series
    or a degenerate bar (the live scan's per-key `except` tolerates these too) sets `skip`."""
    out = {"skip": None}
    if not bars:
        out["skip"] = "no bars for ticker"
        return out
    try:
        return _measure_row(row, bars, out)
    except Exception as e:                    # degenerate data (e.g. a zero close) — counted, not fatal
        return {"skip": f"error:{e.__class__.__name__}"}


def _measure_row(row, bars, out):
    dates = {b["date"]: k for k, b in enumerate(bars)}
    e = dates.get(str(row["entry_date"]))
    if e is None:
        out["skip"] = "entry bar missing"
        return out
    retrace, peak = hold_retrace(bars, e)
    out["retrace"] = retrace
    out["anchor_match"] = (peak == str(row["anchor_date"])) if peak is not None else None
    a = dates.get(str(row["anchor_date"]))
    d = e - ORDERING_ASOF_OFFSET
    out["streak"] = tight_close_streak(bars, d) if d >= 1 else None
    out["today_pct"] = today_pct(bars, d) if d >= 1 else None
    out["rmv_15d"] = compute_rmv(bars, d, lookback=15) if d >= 0 else None
    score, n_gaps, dropped = orderliness_score(bars, a, d)
    out.update(orderliness=score, n_gaps=n_gaps, gaps_dropped=dropped)
    return out


# ═════════════════════════════════════════════════════════════════════════════════════════════════
# Report sections
# ═════════════════════════════════════════════════════════════════════════════════════════════════
def section_3a(label, items):
    print(f"\n  3a HOLD CAP — {label}  (retrace = give-back of the runup leg, live find_coil_setup)")
    cells = hold_cap_cells(items)
    print("     cap    admitted  median R  win rate")
    for c in cells:
        mark = "  <- live" if abs(c["cap"] - INCUMBENT_CAP) < 1e-9 else ""
        print(f"     {c['cap']:.0%}    {c['n']:>8}  {fmt(c['median_r']):>8}  {fmt(c['win_rate'], '.0%'):>8}{mark}")
    above = sum(1 for t, _ in items if t > INCUMBENT_CAP + 1e-12)
    print(f"     note: {above} rows sit above the live {INCUMBENT_CAP:.0%} cap. Names that gave back more "
          f"than {INCUMBENT_CAP:.0%} were never admitted, so never fired: the widen side ({HOLD_CAPS[-1]:.0%}) "
          f"cannot be measured from fired rows.")
    v = hold_cap_verdict(cells, items)
    print(f"  VERDICT 3a [{label}]: {v[0]} — {v[1]}")
    return v


def section_3b(label, ms, rs, q_idx):
    print(f"\n  3b RANK ORDERING — {label}  (keys as of the bar before entry; Spearman vs settled R)")
    keys = [ordering_keys(m, q == 3) for m, q in zip(ms, q_idx)]
    rhos = {}
    for name in ORDERINGS:
        rhos[name] = spearman(board_scores([k[name] for k in keys]), rs)
    print("     ordering                     rho")
    for name in ORDERINGS:
        print(f"     {name:<26} {fmt(rhos[name], '+.3f'):>7}")
    v = ordering_verdict(rhos, len(rs))
    print(f"  VERDICT 3b [{label}]: {v[0]} — {v[1]}")
    return v


def section_3c(label, ms, rs):
    print(f"\n  3c ORDERLINESS — {label}  (P95 overnight gap over the base ÷ ATR14%; Q4 = gappiest)")
    scores = [m["orderliness"] for m in ms]
    known = [k for k, s in enumerate(scores) if s is not None]
    sc = [scores[k] for k in known]
    rr = [rs[k] for k in known]
    print(f"     scored {len(known)} of {len(ms)} (unscored: too few usable gap days or no ATR)")
    table, qi = quartile_table(sc, rr)
    print("     quartile  N    score range      median R  win rate")
    for t in table:
        rng = f"{fmt(t['lo'], '.2f')}–{fmt(t['hi'], '.2f')}"
        print(f"     Q{t['q']}       {t['n']:>3}  {rng:<15}  {fmt(t['median_r']):>8}  {fmt(t['win_rate'], '.0%'):>8}")
    top = [r for r, q in zip(rr, qi) if q == 3]
    rest = [r for r, q in zip(rr, qi) if q is not None and q < 3]
    v = demotion_verdict(top, rest)
    print(f"  VERDICT 3c [{label}]: {v[0]} — {v[1]}")
    return v, table[3]["lo"]                  # Q4's lowest score = the gappy cut (same membership rule)


# ═════════════════════════════════════════════════════════════════════════════════════════════════
# main
# ═════════════════════════════════════════════════════════════════════════════════════════════════
_SHADOW_SQL = """
    SELECT id, ticker, anchor_date, entry_date, entry_price, stop_price, stop_kind, entry_mode,
           origin, outcome, realized_r, realized_r_h12, fwd_mfe_r, rmv_5d, rmv_15d, range_pct,
           vol_ratio, vol_dryup_ratio, regime_at_entry, would_pass_quality
    FROM mi_consolidation_entry_shadow
    ORDER BY entry_date, id"""
_BOARD_SQL = """
    SELECT ticker, anchor_date, state, tight_close_streak, today_pct, rmv_15d, last_eval
    FROM mi_anticipation_consolidation
    WHERE state <> 'aged'"""
_BARS_SQL = """
    SELECT ticker, trade_date, open_price, high_price, low_price, close, volume
    FROM mi_daily_closes
    WHERE ticker = ANY($1::text[]) AND trade_date >= $2 AND trade_date <= $3
    ORDER BY ticker, trade_date"""


def _f(x):
    return float(x) if x is not None else None


def print_identity():
    import agents.market_intelligence.anticipation as A
    try:
        sha = hashlib.sha1(inspect.getsource(find_coil_setup).encode()).hexdigest()[:12]
    except (OSError, TypeError) as e:          # source not shipped in the image — identity still printed
        sha = f"unavailable ({e.__class__.__name__})"
    print("=== MODULE IDENTITY (the live code this run measured) ===")
    print(f"  anticipation: {A.__file__}")
    print(f"  COIL_HOLD_LIMIT={COIL_HOLD_LIMIT}  find_coil_setup sha1={sha}")
    assert abs(COIL_HOLD_LIMIT - INCUMBENT_CAP) < 1e-9, \
        f"live COIL_HOLD_LIMIT={COIL_HOLD_LIMIT} != the method's incumbent {INCUMBENT_CAP}"


def print_composition(rows, today_max):
    print("\n=== 0. POPULATION COMPOSITION (read this first — a surprising trait is an alarm) ===")
    settled = [r for r in rows if r["outcome"] is not None and r[R_COL] is not None]
    ed = [r["entry_date"] for r in rows]
    print(f"  rows {len(rows)} · settled (outcome + {R_COL}) {len(settled)} · "
          f"entry_date {min(ed) if ed else '–'} .. {max(ed) if ed else '–'} · latest bar seen {today_max}")
    grp = defaultdict(list)
    for r in rows:
        grp[(r["origin"], r["entry_mode"], r["stop_kind"])].append(r)
    print(f"  origin     mode        stop            rows  settled  pre-{CORRECTED_BASE_FROM:%m-%d}  "
          f"entry span               median R")
    for (o, m, s), rs in sorted(grp.items()):
        st = [r for r in rs if r["outcome"] is not None and r[R_COL] is not None]
        pre = sum(1 for r in rs if r["entry_date"] < CORRECTED_BASE_FROM)
        span = f"{min(r['entry_date'] for r in rs)}..{max(r['entry_date'] for r in rs)}"
        print(f"  {o:<10} {m:<11} {s:<15} {len(rs):>4}  {len(st):>7}  {pre:>9}  {span:<23}  "
              f"{fmt(median([_f(r[R_COL]) for r in st])):>8}")
    print(f"  outcome: {dict(Counter(r['outcome'] or 'unsettled' for r in rows))}")
    print(f"  regime_at_entry (settled): {dict(Counter(r['regime_at_entry'] or 'NULL' for r in settled))}")
    print(f"  would_pass_quality (settled): {dict(Counter(str(r['would_pass_quality']) for r in settled))}")
    bad_stop = [r for r in rows if r["stop_price"] is not None and r["entry_price"] is not None
                and float(r["stop_price"]) >= float(r["entry_price"])]
    if bad_stop:
        print(f"  ALARM: {len(bad_stop)} rows have stop >= entry (no risk): "
              + ", ".join(f"{r['ticker']} {r['entry_date']}" for r in bad_stop[:8]))
    big = [r for r in settled if abs(float(r[R_COL])) > 15]
    if big:
        print(f"  ALARM: {len(big)} settled rows with |R| > 15: "
              + ", ".join(f"{r['ticker']} {r['entry_date']} {float(r[R_COL]):+.1f}R" for r in big[:8]))
    print(f"  excluded from the tune: origin '9m' ({sum(1 for r in settled if r['origin'] == '9m')} settled — "
          f"composition only); entries before {CORRECTED_BASE_FROM} (pre-coil-finder base) "
          f"({sum(1 for r in settled if r['entry_date'] < CORRECTED_BASE_FROM)} settled)")
    print(f"  R = {R_COL} (the settled R /anticipation reports; legacy 5-day harvest horizon); "
          f"realized_r_h12 (12-bar) is not used.")


def print_fidelity(label, pop):
    n = len(pop)
    skipped = Counter(m["skip"] for _, m in pop if m["skip"])
    measured = [m for _, m in pop if not m["skip"]]
    no_coil = sum(1 for m in measured if m["retrace"] is None)
    mism = sum(1 for m in measured if m["anchor_match"] is False)
    over = sum(1 for m in measured if m["retrace"] is not None and m["retrace"] > INCUMBENT_CAP + 1e-12)
    dropped = sum(m.get("gaps_dropped", 0) for m in measured)
    rate = (mism / len(measured)) if measured else 0.0
    print(f"  fidelity [{label}]: {n} rows · skipped {dict(skipped) or 0} · no coil on recompute {no_coil} · "
          f"anchor mismatch {mism} ({rate:.0%}) · recomputed retrace > {INCUMBENT_CAP:.0%}: {over} · "
          f"NULL-open gap days dropped {dropped}")
    if rate > 0.05 or over:
        print(f"  ALARM [{label}]: the recompute disagrees with what live admitted on "
              f"{mism} anchor(s) / {over} cap breach(es) — read before trusting the 3a sweep")


def live_board_delta(board, open_tickers, bars_by, q3_cutoff):
    print("\n=== 4. TOP-5 BOARD COMPOSITION DELTA (today's 🪙 Coiling section, re-sorted) ===")
    coiled = [b for b in board if b["state"] == "coiled" and b["ticker"] not in open_tickers]
    if not coiled:
        print("  no coiled, non-graduated rows on the board today — nothing to re-sort")
        return
    ms = []
    for b in coiled:
        bars = bars_by.get(b["ticker"], [])
        dates = {x["date"]: k for k, x in enumerate(bars)}
        a = dates.get(str(b["anchor_date"]))
        end = dates.get(str(b["last_eval"])) if b["last_eval"] is not None else None
        try:
            score = orderliness_score(bars, a, end)[0] if bars else None
        except Exception:                     # degenerate bar on a display-only re-sort: unscored, not fatal
            score = None
        ms.append({"ticker": b["ticker"], "streak": b["tight_close_streak"],
                   "today_pct": _f(b["today_pct"]), "rmv_15d": _f(b["rmv_15d"]),
                   "orderliness": score, "last_eval": b["last_eval"]})
    gappy = [m["orderliness"] is not None and q3_cutoff is not None and m["orderliness"] >= q3_cutoff
             for m in ms]
    tops = {}
    for name in ORDERINGS:
        ks = [ordering_keys(m, g)[name] for m, g in zip(ms, gappy)]
        order = sorted(range(len(ms)), key=lambda k: (ks[k], ms[k]["ticker"]))
        tops[name] = [ms[k]["ticker"] for k in order[:5]]
    evals = sorted({str(m["last_eval"]) for m in ms})
    print(f"  {len(ms)} coiled candidates (last_eval {evals[0]}..{evals[-1]}); gappy cut = the lowest score in "
          f"the POOLED settled Q4 ({fmt(q3_cutoff, '.2f')}). The live query also applies LIMIT 25 across "
          f"both states before splitting; this re-sort uses the full coiled set.")
    inc = tops["(i) incumbent"]
    print(f"  {'(i) incumbent':<26} {' '.join(inc)}")
    for name in ORDERINGS[1:]:
        t = tops[name]
        add = [x for x in t if x not in inc]
        drop = [x for x in inc if x not in t]
        print(f"  {name:<26} {' '.join(t)}   (+{','.join(add) or '–'} / −{','.join(drop) or '–'})")


async def main() -> int:
    from agents.market_intelligence.db import get_pool
    print_identity()
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction(readonly=True):
            rows = [dict(r) for r in await conn.fetch(_SHADOW_SQL)]
            board = [dict(r) for r in await conn.fetch(_BOARD_SQL)]
            cohort = [r for r in rows if r["origin"] == "family_a" and r["outcome"] is not None
                      and r[R_COL] is not None and r["entry_date"] >= CORRECTED_BASE_FROM]
            tickers = sorted({r["ticker"] for r in cohort} | {b["ticker"] for b in board})
            starts = [r["entry_date"] for r in cohort] + [b["anchor_date"] for b in board]
            ends = [r["entry_date"] for r in cohort] + [b["last_eval"] for b in board if b["last_eval"]]
            bar_rows = []
            if tickers and starts and ends:
                bar_rows = [dict(r) for r in await conn.fetch(
                    _BARS_SQL, tickers, min(starts) - timedelta(days=BAR_LOOKBACK_DAYS), max(ends))]
    bars_by, bad_bars = bars_by_ticker(bar_rows)
    today_max = max((r["trade_date"] for r in bar_rows), default=None)

    print_composition(rows, today_max)
    if bad_bars:
        print(f"  ALARM: {len(bad_bars)} tickers have unreadable bars and are skipped: "
              + ", ".join(f"{t} ({e})" for t, e in sorted(bad_bars.items())[:12]))
    print(f"\n  TUNE COHORT: {len(cohort)} settled family_a rows from {CORRECTED_BASE_FROM} "
          f"(primary gate N >= {MIN_PRIMARY_N}: {'MET' if len(cohort) >= MIN_PRIMARY_N else 'NOT MET'})")

    measured = [(r, measure_row(r, bars_by.get(r["ticker"], []))) for r in cohort]
    pops = [(lbl, [(r, m) for r, m in measured if r["entry_mode"] == mode and r["stop_kind"] == stop])
            for lbl, mode, stop in POPULATIONS]
    other = [(r, m) for r, m in measured
             if (r["entry_mode"], r["stop_kind"]) not in {(p[1], p[2]) for p in POPULATIONS}]
    if other:
        print(f"  ALARM: {len(other)} cohort rows fit no named population "
              f"{dict(Counter((r['entry_mode'], r['stop_kind']) for r, _ in other))} — POOLED only")
    pops.append((POOLED, measured))

    print("\n=== 1-3. TABLES PER POPULATION (entry modes are never blended; POOLED is the pooling check) ===")
    verdicts = {"3a": {}, "3b": {}, "3c": {}}
    pooled_q3 = None
    for label, pop in pops:
        print(f"\n--- {label} ---")
        print_fidelity(label, pop)
        ok = [(r, m) for r, m in pop if not m["skip"]]
        rs = [_f(r[R_COL]) for r, _ in ok]
        ms = [m for _, m in ok]
        items = [(m["retrace"], _f(r[R_COL])) for r, m in ok if m["retrace"] is not None]
        q_idx = quartile_index([m["orderliness"] for m in ms])   # same membership the 3c table uses
        verdicts["3a"][label] = section_3a(label, items)
        v3b = section_3b(label, ms, rs, q_idx)
        v3c, q4_cut = section_3c(label, ms, rs)
        verdicts["3b"][label], verdicts["3c"][label] = v3b, v3c
        if label == POOLED:
            pooled_q3 = q4_cut
        if (v3c[0] == "DEMOTE") != (v3b[0] == "ADOPT (iv)"):
            print(f"  NOTE [{label}]: 3c says {v3c[0]} but 3b's (iv) adoption says {v3b[0]} — the method has "
                  f"two rules for the same demotion; both shown, neither overrides the other.")

    open_tickers = {r["ticker"] for r in rows if r["outcome"] is None}
    live_board_delta(board, open_tickers, bars_by, pooled_q3)

    print("\n=== 5. KNOB VERDICTS (per-knob honesty: a decisive cell N < 10 -> unchanged) ===")
    for knob, name in (("3a", "HOLD CAP"), ("3b", "RANK ORDERING"), ("3c", "ORDERLINESS demotion")):
        per = {p: v for p, v in verdicts[knob].items() if p != POOLED}
        final = combine_verdicts(per)
        pooled = verdicts[knob][POOLED]
        changes = "yes" if action_of(pooled[0]) != final[0] else "no"
        print(f"  KNOB {knob} {name}: {final[0]} — {final[1]}")
        print(f"      POOLED verdict: {pooled[0]} · POOLING CHANGES VERDICT: {changes}")
    return 0


# ═════════════════════════════════════════════════════════════════════════════════════════════════
# --selftest (hand cases; no DB)
# ═════════════════════════════════════════════════════════════════════════════════════════════════
def _bar(d, c, *, o=None, hl=0.01, v=1_000_000.0, o_missing=False):
    return {"date": d, "o": c if o is None else o, "h": c * (1 + hl), "l": c * (1 - hl), "c": c,
            "v": v, "o_missing": o_missing}


def _series_bars(closes):
    d0 = date(2026, 1, 1)
    return [_bar((d0 + timedelta(days=k)).isoformat(), c) for k, c in enumerate(closes)]


def selftest() -> int:
    fails = []

    def check(name, cond, detail=""):
        print(f"  {'PASS' if cond else 'FAIL'}  {name}{('  ' + detail) if detail else ''}")
        if not cond:
            fails.append(name)

    print("selftest — #394 coil tune probe")
    # percentile: numpy-linear
    check("percentile P95 of 1..5 = 4.8", abs(percentile([1, 2, 3, 4, 5], 95) - 4.8) < 1e-9)
    check("percentile of one value is that value", percentile([7.0], 95) == 7.0)

    # live hold retrace on the coil-finder's own test shape: 100 -> 130 leg, coil at 125 (lows 123.75)
    bars = _series_bars([100.0] * 30 + [100.0 + 3.0 * (k + 1) for k in range(10)] + [125.0] * 15)
    t, peak = hold_retrace(bars, len(bars) - 1)
    check("hold retrace = (130 - 123.75) / 30 via live find_coil_setup",
          t is not None and abs(t - 6.25 / 30) < 1e-9 and peak == bars[39]["date"], f"got {t}, {peak}")
    deep = _series_bars([100.0] * 30 + [100.0 + 3.0 * (k + 1) for k in range(10)] + [112.0] * 15)
    t2, _ = hold_retrace(deep, len(deep) - 1)
    check("deep give-back reads above the 50% cap", t2 is not None and t2 > 0.50, f"got {t2}")

    # orderliness: flat closes at 100, TR = 2 (hl 1%) -> ATR14% = 2.0; gaps 0,0,1,0,3 % -> P95 = 2.6
    ob = _series_bars([100.0] * 30)
    for k, o in zip(range(21, 26), (100.0, 100.0, 101.0, 100.0, 103.0)):
        ob[k]["o"] = o
    s, n, dropped = orderliness_score(ob, 20, 25)
    # day 25's TR = max(h-l, |h-c_prev|, |l-c_prev|) = 2 (open is not in TR) -> ATR14% = 2.0
    check("orderliness = P95(gaps)/ATR14% = 2.6/2.0", s is not None and abs(s - 1.3) < 1e-9 and n == 5,
          f"got {s}, n={n}")
    ob[25]["o_missing"] = True
    s3, n3, d3 = orderliness_score(ob, 20, 25)
    check("NULL-open day is dropped, not read as a gap", d3 == 1 and n3 == 4 and abs(s3 - 0.85 / 2.0) < 1e-9,
          f"got {s3}, n={n3}, dropped={d3}")
    check("too few gap days -> unknown", orderliness_score(ob, 22, 24)[0] is None)

    # Spearman
    check("spearman perfect = +1", abs(spearman([1, 2, 3, 4], [10, 20, 30, 40]) - 1) < 1e-12)
    check("spearman reversed = -1", abs(spearman([1, 2, 3, 4], [4, 3, 2, 1]) + 1) < 1e-12)
    check("spearman ties use average ranks", abs(spearman([1, 1, 2, 3], [1, 2, 3, 4]) - 0.9486832980505138) < 1e-9)
    check("spearman constant side -> None", spearman([1, 1, 1], [1, 2, 3]) is None)
    check("board score: streak 5 above streak 2 above None",
          board_scores([(-5,), (-2,), (_INF,)]) == [-1.0, -2.0, -3.0])

    # 3a rule (R must be SPREAD inside the 40% cell: under the 30% recall guard a constant-R cell
    # pins every cap's median to the same value)
    def spread(n, lo, hi):
        return [lo + (hi - lo) * k / (n - 1) for k in range(n)]

    move = [(0.2, r) for r in spread(40, -1.0, 2.0)] + [(0.45, -2.0)] * 12
    v = hold_cap_verdict(hold_cap_cells(move), move)
    check("3a: tighter cap with better median + band N=12 -> MOVE to 40%", v[0] == "MOVE 40%", v[1])
    guard = [(0.2, 2.0)] * 10 + [(0.45, 0.2)] * 30
    v = hold_cap_verdict(hold_cap_cells(guard), guard)
    check("3a: recall guard (40% cuts 75%) -> KEEP", v[0] == "KEEP", v[1])
    knife = [(0.2, 0.5)] * 30 + [(0.45, -1.0)] * 40
    v = hold_cap_verdict(hold_cap_cells(knife), knife)
    check("3a: adjacent cells opposite sign -> KNIFE-EDGE", v[0] == "KNIFE-EDGE", v[1])
    thin = [(0.2, r) for r in spread(60, -1.0, 2.0)] + [(0.45, -2.0)] * 6
    v = hold_cap_verdict(hold_cap_cells(thin), thin)
    check("3a: marginal band N=6 -> INSUFFICIENT", v[0] == "INSUFFICIENT" and "6 rows" in v[1], v[1])
    flat = [(0.2, r) for r in spread(30, -1.0, 2.0)]
    v = hold_cap_verdict(hold_cap_cells(flat), flat)
    check("3a: 60% cell == 50% cell (nothing above the cap fired) -> KEEP", v[0] == "KEEP", v[1])

    # 3b rule
    v = ordering_verdict({"(i) incumbent": 0.05, "(ii) rmv-led": 0.21, "(iii) streak-led": 0.0}, 40)
    check("3b: gap 0.16 >= 0.15 -> ADOPT (ii)", v[0] == "ADOPT (ii)", v[1])
    v = ordering_verdict({"(i) incumbent": 0.05, "(ii) rmv-led": 0.19}, 40)
    check("3b: gap 0.14 -> KEEP", v[0] == "KEEP", v[1])
    v = ordering_verdict({"(i) incumbent": 0.05, "(ii) rmv-led": 0.9}, 19)
    check("3b: N=19 -> INSUFFICIENT", v[0] == "INSUFFICIENT", v[1])

    # 3c rule + quartiles
    qi = quartile_index([5, 1, 8, 3, None, 7, 2, 6])
    check("quartile_index: rank-based, None stays None", qi == [1, 0, 3, 1, None, 2, 0, 2], str(qi))
    check("quartile_index: n=8 splits 2/2/2/2", sorted(quartile_index(list(range(8)))) == [0, 0, 1, 1, 2, 2, 3, 3])
    v = demotion_verdict([-1.0] * 10, [0.0] * 30)
    check("3c: top trails rest by 1.0R at N>=10 -> DEMOTE", v[0] == "DEMOTE", v[1])
    v = demotion_verdict([-0.4] * 10, [0.0] * 30)
    check("3c: trail 0.4R -> NO-DEMOTE", v[0] == "NO-DEMOTE", v[1])
    v = demotion_verdict([-3.0] * 9, [0.0] * 30)
    check("3c: top N=9 -> INSUFFICIENT", v[0] == "INSUFFICIENT", v[1])

    # combining
    check("combine: voters agree", combine_verdicts({"a": ("KEEP", ""), "b": ("KEEP", ""),
                                                     "c": ("INSUFFICIENT", "")})[0] == "NO CHANGE")
    check("combine: KEEP + KNIFE-EDGE both mean no change", combine_verdicts(
        {"a": ("KEEP", ""), "b": ("KNIFE-EDGE", "")})[0] == "NO CHANGE")
    check("combine: voters disagree -> SPLIT",
          combine_verdicts({"a": ("KEEP", ""), "b": ("MOVE 40%", "")})[0] == "SPLIT")
    check("combine: two different moves -> SPLIT",
          combine_verdicts({"a": ("MOVE 40%", ""), "b": ("MOVE 60%", "")})[0] == "SPLIT")
    check("combine: nobody votes -> UNCHANGED", combine_verdicts({"a": ("INSUFFICIENT", "")})[0] == "UNCHANGED")

    print(f"selftest: {'OK' if not fails else 'FAILED'} ({len(fails)} failed)")
    return 0 if not fails else 1


if __name__ == "__main__":
    if "--selftest" in sys.argv[1:]:
        sys.exit(selftest())
    import asyncio
    sys.exit(asyncio.run(main()))
