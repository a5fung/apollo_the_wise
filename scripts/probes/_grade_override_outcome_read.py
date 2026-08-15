"""Does the gap-floor's override of the holistic judge cost money?

READ-ONLY. No trading, no writes, no LLM spend. Answers path step 4b of The Real
EP Plan (docs/roadmap/ep_profitability_program.md).

THE QUESTION. `_score_ep`'s conviction floor forces a HIGH-range score on
gap+catalyst alone, and it can outrank the holistic judge. Measured: alerts fired
HIGH while the judge graded them `none` or `MODERATE`. Did those overridden names
do WORSE than the HIGHs the judge agreed with?

THE CONFOUND, AND THE DESIGN THAT HANDLES IT. The floor only binds at gap >=15%
(>=10% for game_changer), so the overridden cohort is big-gap BY CONSTRUCTION. A
naive A-vs-B difference would conflate "the override is bad" with "big gaps are
bad". So the headline comparison is run WITHIN gap bands — overridden vs agreed
at comparable gap — and the unmatched read is reported alongside, labelled.

WHAT WOULD MAKE THIS CONCLUSIVE, STATED UP FRONT (operator 2026-08-15: "i won't
say it's conclusive yet until we can truly separate noise and chance from real
alpha, though the data can still be informative"). It would need: (a) a
difference that survives a permutation test on SESSIONS, not rows — alerts on the
same morning are not independent draws; (b) N per band large enough that the
median is stable; (c) the same sign across horizons. This probe reports all
three so a null is as readable as a hit. It does not decide anything: grading is
a detection criterion = THE LINE + CHANGE_PROCESS.
"""
from __future__ import annotations

import json
import os
import random
import statistics as st
import subprocess
import sys

HOST = "apollo@87.99.134.162"
DATA_MAX = ""
RANDOM_SEED = 20260815          # fixed: the permutation p must be reproducible
N_PERM = 20000
HORIZONS = ["ret_1d", "ret_5d", "ret_20d", "max_high_5d", "max_high_20d"]
# ⚠ The outcome columns are FRACTIONS (0.0547 = +5.47%), not percents — display x100.
# ⚠ A horizon is only MATURE once that many calendar days have passed since the alert;
# an 08-07 alert's "20d" value is really its 5d value. Immature rows are DROPPED per
# horizon rather than silently averaged in (they bias every long horizon toward 0).
MATURITY_DAYS = {"ret_1d": 2, "ret_5d": 8, "ret_20d": 30, "max_high_5d": 8, "max_high_20d": 30}
# The floor's own binding conditions (ep_detector._score_ep) — bands chosen to
# straddle them rather than to flatter the result.
BANDS = [(10.0, 15.0), (15.0, 20.0), (20.0, 1e9)]

SQL = """
SELECT a.alert_date, a.ticker, a.gap_pct, a.score_tier, a.judge_tier,
       coalesce(a.grade_engine_authority,'(null)') AS authority,
       a.catalyst_quality,
       m.ret_1d, m.ret_5d, m.ret_20d, m.max_high_5d, m.max_high_20d
FROM mi_ep_alerts a
LEFT JOIN mi_ep_missed_outcomes m
  ON m.ticker = a.ticker AND m.alert_date = a.alert_date
WHERE a.judge_tier IS NOT NULL
ORDER BY a.alert_date, a.ticker
"""


def fetch() -> list[dict]:
    out = subprocess.run(
        ["ssh", "-o", "ConnectTimeout=20", HOST,
         "docker exec apollo-postgres psql -U apollo -d apollo -t -A -F'|' -c "
         + json.dumps(SQL.replace("\n", " "))],
        capture_output=True, text=True, timeout=180)
    if out.returncode != 0:
        sys.exit(f"query failed: {out.stderr[:500]}")
    cols = ["alert_date", "ticker", "gap_pct", "score_tier", "judge_tier", "authority",
            "catalyst_quality", "ret_1d", "ret_5d", "ret_20d", "max_high_5d", "max_high_20d"]
    rows = []
    for line in out.stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split("|")
        if len(parts) != len(cols):
            continue
        r = dict(zip(cols, parts))
        for k in ["gap_pct"] + HORIZONS:
            r[k] = float(r[k]) if r[k] not in ("", None) else None
        rows.append(r)
    return rows


def cohort(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """OVERRIDDEN = the FLOOR held authority and fired HIGH over a LOWER judge verdict.

    The authority filter is load-bearing: a row where the judge itself held authority
    is not an override no matter what the tiers say, and counting it would inflate the
    cohort with the engine's own decisions.
    """
    over = [r for r in rows if r["score_tier"] == "HIGH"
            and r["judge_tier"] in ("none", "MODERATE")
            and r["authority"] == "floor"]
    agree = [r for r in rows if r["score_tier"] == "HIGH" and r["judge_tier"] == "HIGH"]
    return over, agree


def mature(rows: list[dict], h: str, data_max: str) -> list[dict]:
    """Drop alerts too recent for horizon h to have actually elapsed."""
    from datetime import date, timedelta
    y, m, d = (int(x) for x in data_max.split("-"))
    cutoff = date(y, m, d) - timedelta(days=MATURITY_DAYS[h])
    out = []
    for r in rows:
        yy, mm, dd = (int(x) for x in r["alert_date"].split("-"))
        if date(yy, mm, dd) <= cutoff:
            out.append(r)
    return out


def perm_p(a: list[float], b: list[float], sess_a: list[str], sess_b: list[str]) -> float | None:
    """Permutation test on the difference in MEDIANS, shuffling whole SESSIONS.

    Alerts on the same morning share the tape, the regime and often the catalyst
    theme — they are not independent draws, and a row-level shuffle would report a
    p an order of magnitude too small. Sessions are the exchangeable unit here.
    """
    by_sess: dict[str, list[tuple[float, int]]] = {}
    for v, s in zip(a, sess_a):
        by_sess.setdefault(s, []).append((v, 0))
    for v, s in zip(b, sess_b):
        by_sess.setdefault(s, []).append((v, 1))
    sessions = sorted(by_sess)
    n_a = len(a)
    if n_a < 5 or len(b) < 5 or len(sessions) < 6:
        return None
    obs = st.median(a) - st.median(b)
    rng = random.Random(RANDOM_SEED)
    hits = 0
    pool = [(s, [v for v, _ in by_sess[s]]) for s in sessions]
    counts = [len(by_sess[s]) for s in sessions]
    for _ in range(N_PERM):
        idx = list(range(len(sessions)))
        rng.shuffle(idx)
        take, got = [], 0
        for i in idx:                      # assign whole sessions to "A" until size matches
            if got >= n_a:
                break
            take.append(i)
            got += counts[i]
        takeset = set(take)
        pa = [v for i in takeset for v in pool[i][1]]
        pb = [v for i in range(len(sessions)) if i not in takeset for v in pool[i][1]]
        if not pa or not pb:
            continue
        if abs(st.median(pa) - st.median(pb)) >= abs(obs):
            hits += 1
    return (hits + 1) / (N_PERM + 1)


def describe(rows: list[dict], h: str) -> dict:
    vals = [r[h] * 100.0 for r in rows if r[h] is not None]
    sess = {r["alert_date"] for r in rows if r[h] is not None}
    if not vals:
        return {"n": 0, "sessions": 0}
    return {"n": len(vals), "sessions": len(sess), "median": round(st.median(vals), 2),
            "mean": round(st.fmean(vals), 2),
            "p25": round(sorted(vals)[len(vals) // 4], 2),
            "p75": round(sorted(vals)[3 * len(vals) // 4], 2),
            "pct_positive": round(100.0 * sum(1 for v in vals if v > 0) / len(vals), 1)}


def main() -> None:
    global DATA_MAX
    rows = fetch()
    DATA_MAX = max(r["alert_date"] for r in rows)
    over, agree = cohort(rows)
    print("=" * 78)
    print("GRADE-OVERRIDE OUTCOME READ — does the gap-floor's override cost money?")
    print("=" * 78)
    win = [r["alert_date"] for r in rows]
    print(f"window {min(win)} .. {max(win)} · {len(rows)} judged alerts · "
          f"{len({r['alert_date'] for r in rows})} sessions")
    cov = sum(1 for r in over + agree if r["ret_5d"] is not None)
    print(f"cohorts: OVERRIDDEN {len(over)} (fired HIGH over a lower judge verdict) · "
          f"AGREED {len(agree)} (judge said HIGH) · outcome coverage {cov}/{len(over)+len(agree)}")
    from collections import Counter
    print("authority mix — overridden: "
          + str(dict(Counter(r["authority"] for r in over)))
          + " · agreed: " + str(dict(Counter(r["authority"] for r in agree))))
    print("⚠ values are FRACTIONS in the DB and are printed x100 as real percents.")
    print("⚠ each horizon drops alerts too recent to have elapsed (a 08-07 alert has no")
    print("  real 20-day outcome yet) — that is why N falls as the horizon lengthens.")
    print("\n⚠ The overridden cohort is big-gap BY CONSTRUCTION (the floor only binds at")
    print("  gap>=15%, or >=10% for game_changer). The banded read below is the honest one;")
    print("  the pooled read is reported first only to show the size of the confound.\n")

    for label, sel in [("POOLED (confounded — read the bands instead)", None)] + \
                      [(f"GAP {lo:.0f}-{hi:.0f}%" if hi < 1e8 else f"GAP >={lo:.0f}%", (lo, hi))
                       for lo, hi in BANDS]:
        o_all = over if sel is None else [r for r in over if r["gap_pct"] is not None
                                          and sel[0] <= r["gap_pct"] < sel[1]]
        a_all = agree if sel is None else [r for r in agree if r["gap_pct"] is not None
                                           and sel[0] <= r["gap_pct"] < sel[1]]
        print("-" * 78)
        print(f"{label}   overridden n={len(o_all)}  agreed n={len(a_all)}")
        if not o_all or not a_all:
            print("  (empty cohort — nothing to compare)")
            continue
        for h in HORIZONS:
            o, a = mature(o_all, h, DATA_MAX), mature(a_all, h, DATA_MAX)
            do, da = describe(o, h), describe(a, h)
            if not do["n"] or not da["n"]:
                continue
            vo = [r[h] * 100.0 for r in o if r[h] is not None]
            va = [r[h] * 100.0 for r in a if r[h] is not None]
            so = [r["alert_date"] for r in o if r[h] is not None]
            sa = [r["alert_date"] for r in a if r[h] is not None]
            p = perm_p(vo, va, so, sa)
            pstr = "N too small" if p is None else f"p={p:.3f}"
            print(f"  {h:<13} overridden med {do['median']:>7}%  (n={do['n']:>3}, "
                  f"{do['sessions']:>2} sess, {do['pct_positive']:>5}% up)   "
                  f"agreed med {da['median']:>7}%  (n={da['n']:>3}, {da['sessions']:>2} sess, "
                  f"{da['pct_positive']:>5}% up)   {pstr}")

    print("=" * 78)
    print("HOW TO READ THIS — the permutation p shuffles whole SESSIONS, not rows, because")
    print("alerts on one morning share the tape. A p above ~0.1 with these N's means the")
    print("difference is inside what chance produces; that is INFORMATIVE, not a verdict.")
    print("Nothing here licenses a grading change — that is a detection criterion (THE LINE).")


if __name__ == "__main__":
    if os.environ.get("APOLLO_PROBE_WRITE"):
        sys.exit("this probe is read-only by design")
    main()
