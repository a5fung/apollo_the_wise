#!/usr/bin/env python3
"""Shared TAIL-STATISTIC machinery for the 2026-08-16 tail re-read
(docs/roadmap/ep_profitability_program.md GOAL section "WE ARE HUNTING THE TAIL, NOT THE
AVERAGE" — operator 2026-08-16: medians are blind to a tail by construction).

Generalizes the house median-permutation pattern (identical across _533_supply_ladder_probe.py,
_rs_inflection_read.py, _grade_override_outcome_read.py, _skip_attribution_read.py,
_533_nbis_structure_encoder.py's run_sweep) to an arbitrary statistic, so P90/P95/share-
reaching-a-threshold can be permutation-tested the same way medians already are: whole
SESSIONS shuffled (same-morning alerts share the tape, not independent draws), same seed,
same N_PERM as every other probe in this program.

READ-ONLY. Pure local computation over already-cached values. No prod pull, no writes, no
LLM spend. Nothing here is wired into any grade, admission rule, sizing, or exit — THE LINE.

RIGOR ON TAILS (why the floor is stricter than the median version). A permuted P90/P95
statistic is pinned to one of the top few order statistics in the resampled bucket, so it
takes on far FEWER distinct values across N_PERM draws than a permuted median does — the
exact discreteness _skip_attribution_read.py's MIN_DISTINCT_PERM_STATS guard (its own
perm_p, lines 356-410) was built to catch for one extreme size-imbalance case shows up
routinely for quantiles. The same floor (50 distinct achieved statistic values across
20,000 draws) is carried forward here for EVERY statistic tested, not just the median, and
additional descriptive-only floors gate P90/P95/share reporting before a permutation is
even attempted (MIN_N_P90/P95/SHARE below) — a p from too few order statistics is precise-
looking, not trustworthy.
"""
from __future__ import annotations

import random
import statistics as st
from collections import defaultdict

SEED = 20260815
N_PERM = 20000
MIN_DISTINCT_PERM_STATS = 50

# Descriptive-reporting floors — below these, DO NOT attempt a permutation p for that
# statistic; report the raw count/N and say "N too thin for a tail read", per the task's
# own rigor line ("a tail statistic needs far more N than a median").
MIN_N_P90 = 20
MIN_N_P95 = 40
MIN_N_SHARE = 10


def pct(vals: list[float], q: float) -> float | None:
    """Nearest-rank percentile (same rounding convention as the p25/p75 already used in
    _grade_override_outcome_read.py / _skip_attribution_read.py: sorted()[frac*len])."""
    if not vals:
        return None
    s = sorted(vals)
    k = max(0, min(len(s) - 1, round(q / 100.0 * (len(s) - 1))))
    return s[k]


def p90(vals: list[float]) -> float | None:
    return pct(vals, 90)


def p95(vals: list[float]) -> float | None:
    return pct(vals, 95)


def share_ge(vals: list[float], thresh: float) -> tuple[int, float | None]:
    """(hit_count, share_pct). ALWAYS carry the count beside the share — a lone '3.3%'
    hides whether that is 4-of-120 or 1-of-30 (a share needs its numerator to be read)."""
    if not vals:
        return 0, None
    hits = sum(1 for v in vals if v >= thresh)
    return hits, round(100.0 * hits / len(vals), 1)


def share_stat(thresh: float):
    """statfn usable with perm_p_stat: the SHARE (0-100 scale) of a list reaching >=thresh."""
    def _f(vals: list[float]) -> float:
        _, s = share_ge(vals, thresh)
        return s if s is not None else 0.0
    return _f


def describe_tail(vals: list[float], sess: set | None = None) -> dict:
    """vals already in PERCENT units (x100 applied by the caller — house convention).
    median is reported as the SECONDARY per the task; p90/p95/share are the primaries,
    each individually gated on N (None when too thin, never silently substituted)."""
    n = len(vals)
    if not n:
        return dict(n=0, sessions=(len(sess) if sess is not None else 0), median=None,
                    p90=None, p95=None, hit50=0, share50=None, hit100=0, share100=None)
    h50, s50 = share_ge(vals, 50.0)
    h100, s100 = share_ge(vals, 100.0)
    return dict(
        n=n, sessions=(len(sess) if sess is not None else None),
        median=round(st.median(vals), 2),
        p90=(round(pct(vals, 90), 2) if n >= MIN_N_P90 else None),
        p95=(round(pct(vals, 95), 2) if n >= MIN_N_P95 else None),
        hit50=h50, share50=(s50 if n >= MIN_N_SHARE else None),
        hit100=h100, share100=(s100 if n >= MIN_N_SHARE else None),
    )


def perm_p_stat(a, b, sess_a, sess_b, statfn, seed=SEED, n_perm=N_PERM,
                 min_n=5, min_sessions=6, min_distinct=MIN_DISTINCT_PERM_STATS) -> float | None:
    """Permutation test on an ARBITRARY statistic difference statfn(list)->float, whole
    SESSIONS shuffled (house convention, mechanically identical to every probe's own
    perm_p — generalized past a hardcoded st.median so the significance test matches
    whichever statistic is being reported, per the task's instruction). Returns None
    ('N too small' / 'too coarse to trust') on the same two size gates the house perm_p
    uses, PLUS the distinct-achieved-statistic-values floor documented above."""
    by_sess: dict[str, list[float]] = defaultdict(list)
    for v, s in zip(a, sess_a):
        by_sess[s].append(v)
    for v, s in zip(b, sess_b):
        by_sess[s].append(v)
    sessions = sorted(by_sess)
    n_a = len(a)
    if n_a < min_n or len(b) < min_n or len(sessions) < min_sessions:
        return None
    obs = statfn(a) - statfn(b)
    rng = random.Random(seed)
    counts = [len(by_sess[s]) for s in sessions]
    pool = [by_sess[s] for s in sessions]
    hits = 0
    distinct: set[float] = set()
    for _ in range(n_perm):
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
        stat = statfn(pa) - statfn(pb)
        distinct.add(round(stat, 6))
        if abs(stat) >= abs(obs):
            hits += 1
    if len(distinct) < min_distinct:
        return None
    return (hits + 1) / (n_perm + 1)


class TailLedger:
    """Counts every tail-statistic test attempted, mirroring each probe's own
    TESTS_ATTEMPTED/TESTS_COMPLETED multiplicity ledger, kept SEPARATE per probe (never
    pooled into someone else's Bonferroni denominator)."""
    def __init__(self, name: str):
        self.name = name
        self.attempted = 0
        self.completed = 0
        self.results: list[dict] = []

    def add(self, label: str, stat_name: str, h: str, pos: dict, neg: dict, p: float | None,
            effect: float | None, thin: bool = False):
        self.attempted += 1
        if p is not None:
            self.completed += 1
        self.results.append(dict(label=label, stat=stat_name, h=h, pos=pos, neg=neg, p=p,
                                  effect=effect, thin=thin))

    def bonferroni_summary(self) -> str:
        n = self.attempted
        sig_raw = [r for r in self.results if r["p"] is not None and r["p"] < 0.05]
        sig_adj = [r for r in self.results if r["p"] is not None and r["p"] * n < 0.05]
        lines = [f"  [{self.name}] tail tests attempted: {n}, {self.completed} produced a p",
                 f"    raw p<0.05: {len(sig_raw)}"
                 + (" — " + "; ".join(f"{r['label']}/{r['stat']} (p={r['p']:.3f})" for r in sig_raw)
                    if sig_raw else ""),
                 f"    surviving Bonferroni x{n}: {len(sig_adj)}"
                 + (" — " + "; ".join(f"{r['label']}/{r['stat']}" for r in sig_adj)
                    if sig_adj else " — NONE")]
        return "\n".join(lines)


def fmt_bucket(d: dict) -> str:
    if not d["n"]:
        return "n=0"
    sess = f"{d['sessions']}s" if d.get("sessions") is not None else "?s"
    p90s = f"{d['p90']:+.1f}%" if d["p90"] is not None else "N<20"
    p95s = f"{d['p95']:+.1f}%" if d["p95"] is not None else "N<40"
    s50 = f"{d['share50']}%({d['hit50']})" if d["share50"] is not None else f"N<10({d['hit50']})"
    s100 = f"{d['share100']}%({d['hit100']})" if d["share100"] is not None else f"N<10({d['hit100']})"
    return (f"n={d['n']:>4} ({sess:>4}) med(2ndry)={d['median']:>7}% "
            f"P90={p90s:>8} P95={p95s:>8} share>=+50%={s50:<14} share>=+100%={s100}")
