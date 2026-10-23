"""#705 (c) - the GOLDEN SYNTHETIC FIXTURES of the RS-alone read (spec check 9): the `rs_best` TIE at the cutoff value, every expectation HAND-COMPUTED
from the mid-rank formula in closed form - never from the engine.

The rule the doc discloses and these fixtures pin: a fill is scored against the pool (n fills, itself not in it) by pct = (worse + 0.5 x equal) / n; a
pool member is a REFERENCE score against the pool minus itself, (worse + 0.5 x equal-without-itself) / (n - 1). A fill whose pct p is above one half
therefore scores BELOW every member tied with it - that member's pct is p + (p - 1/2) / (n - 1) - so a fill tied with the cutoff member at the cutoff's
own value is NOT A+: the boundary moves to strictly above the 12th member's value when it is shared.

Three days, each with its own pool of 40 pool-only fills over the 20 prior sessions (2 per session), 100 sessions apart:
  T1  distinct pool 50..89 (the member at 78.0 holds the 12th-highest reference score, 28/39). The fill AT 78.0 scores 28.5/40 < 28/39 -> rest; 78.1 scores
      29/40 -> A+; 85.0, 89.5 -> A+ (the third); 100.0 -> capped (the 4th fill above the cutoff in a week); 77.9 -> rest; 60.0 (a tie BELOW one half) scores
      ABOVE its tied member (10.5/40 > 10/39) - the rule is not "a tie always loses".
  T2  the cutoff value is SHARED by six members (55..80 distinct, six at 81.0, 82..89 distinct): the cutoff member's score is 28.5/39. The fill AT 81.0 scores
      29/40 < 28.5/39 -> rest; 81.05 scores 32/40 -> A+.
  T3  the top value held by FOURTEEN members (55..80, fourteen at 100.0): the cutoff is 32.5/39 and a fill AT 100.0 - the maximum - scores 33/40 below it:
      no fill is A+ that day, though every value is rated.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

N_POOL = 40
T1_CI, T2_CI, T3_CI = 150, 250, 350
CAL_START = dt.date(2024, 6, 24)


def calendar(n: int = 400, start: dt.date = CAL_START) -> list:
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += dt.timedelta(days=1)
    return out


CAL = calendar()


@dataclass
class FRow:
    ticker: str
    E_ci: int
    fill_minute: int
    rs_best: float
    eligible: bool = True

    @property
    def E(self) -> str:
        return CAL[self.E_ci]


def pool_values(day: str) -> list:
    if day == "T1":
        return [50.0 + i for i in range(40)]
    if day == "T2":
        return [55.0 + i for i in range(26)] + [81.0] * 6 + [82.0 + i for i in range(8)]
    if day == "T3":
        return [55.0 + i for i in range(26)] + [100.0] * 14
    raise ValueError(day)


E_OF = {"T1": T1_CI, "T2": T2_CI, "T3": T3_CI}
# (ticker, fill_minute, rs_best, the flag the hand computation gives)
FILLS = {"T1": [("A", 5, 78.0, "rest"), ("B", 6, 78.1, "aplus"), ("C", 7, 85.0, "aplus"), ("D", 8, 89.5, "aplus"), ("E", 9, 100.0, "capped"),
                ("F", 10, 77.9, "rest"), ("G", 11, 60.0, "rest")],
         "T2": [("A", 5, 81.0, "rest"), ("B", 6, 80.9, "rest"), ("C", 7, 81.05, "aplus"), ("D", 8, 90.0, "aplus")],
         "T3": [("A", 5, 100.0, "rest"), ("B", 6, 99.9, "rest"), ("C", 7, 100.0, "rest")]}
# the value of the cutoff member and the number of fills sitting exactly at it (the STEP 0 "ties at the cutoff" count, by hand)
CUTOFF_VALUE = {"T1": 78.0, "T2": 81.0, "T3": 100.0}
TIES = {"T1": 1, "T2": 1, "T3": 2}


def golden_rows() -> list:
    rows = []
    for day, e in E_OF.items():
        for i, v in enumerate(pool_values(day)):
            rows.append(FRow(f"{day}P{i:02d}", e - 20 + i // 2, 5, v, eligible=False))
        for t, fm, v, _flag in FILLS[day]:
            rows.append(FRow(f"{day}{t}", e, fm, v))
    rows.sort(key=lambda r: (r.E_ci, r.fill_minute, r.ticker))
    return rows


def cols_of(rows: list) -> dict:
    """The engine's input for `rows` (in fill order): identity, week and order columns + rs_best, every other feature column padded with None."""
    from scripts.probes._cb_backtest import aplus_read as ap
    from scripts.probes._cb_backtest import rs_alone_read as rs
    base = {"ticker": [r.ticker for r in rows], "E": [r.E for r in rows], "E_ci": [r.E_ci for r in rows], "fill_minute": [r.fill_minute for r in rows],
            "week": [ap.iso_week(r.E) for r in rows], "eligible": [r.eligible for r in rows]}
    return rs.engine_cols(base, [r.rs_best for r in rows])


# ═══ the hand computation (closed form from the mid-rank formula; never the engine) ═══════════════════════════════════════════════════
def hand_pct(values: list, x: float, exclude_self: bool = False) -> float:
    """(worse + 0.5 x equal) / |S|, x itself removed once from the pool when `exclude_self` (the leave-one-out reference score)."""
    S = list(values)
    if exclude_self:
        S.remove(x)
    worse = sum(1 for v in S if v < x)
    eq = sum(1 for v in S if v == x)
    return (worse + 0.5 * eq) / len(S)


def hand_day(day: str) -> dict:
    pool = pool_values(day)
    ref = sorted((hand_pct(pool, v, exclude_self=True) for v in pool), reverse=True)
    return {"cutoff": ref[11], "fills": {f"{day}{t}": hand_pct(pool, v) for t, _fm, v, _f in FILLS[day]}}


def _close(a, b, tol=1e-12) -> bool:
    if a is None or b is None or a != a or b != b:
        return (a is None or a != a) and (b is None or b != b)
    return abs(float(a) - float(b)) <= tol


def run_golden() -> list:
    """Every golden expectation against the engine; returns the problems (empty = check 9 passes)."""
    from scripts.probes._cb_backtest import aplus_read as ap
    from scripts.probes._cb_backtest import rs_alone_read as rs
    P = []
    rows = golden_rows()
    cols = cols_of(rows)
    res = rs.rate_alone(cols)
    ties = rs.ties_at_cutoff(cols, res)
    idx = {t: i for i, t in enumerate(cols["ticker"])}
    fl = rs.flags(res)
    if set(res["score"]) != {rs.RS_SPEC}:
        P.append(f"the engine rated {sorted(res['score'])}, not {rs.RS_SPEC} alone")
    for day in E_OF:
        hd = hand_day(day)
        n = N_POOL
        for t, fm, v, want_flag in FILLS[day]:
            tk = f"{day}{t}"
            i = idx[tk]
            if not _close(res["score"][rs.RS_SPEC][i], hd["fills"][tk]):
                P.append(f"{day}: {tk}'s score {res['score'][rs.RS_SPEC][i]!r} != hand {hd['fills'][tk]!r}")
            if not _close(res["cutoff"][(rs.RS_SPEC, rs.RS_N)][i], hd["cutoff"]):
                P.append(f"{day}: {tk}'s cutoff {res['cutoff'][(rs.RS_SPEC, rs.RS_N)][i]!r} != the hand-computed 12th-highest reference score {hd['cutoff']!r}")
            if fl[i] != want_flag:
                P.append(f"{day}: {tk} (rs_best {v}) reads {fl[i]!r}, not {want_flag!r}")
        if any(fl[idx[f"{day}P{i:02d}"]] != ap.FLAG_POOL for i in range(N_POOL)):
            P.append(f"{day}: a pool-only member carries a flag")
        # the closed form the doc discloses: a tied fill with p > 1/2 scores below the member it ties with, by exactly (p - 1/2) / (n - 1)
        a = f"{day}A"
        v_a = next(v for t, _fm, v, _f in FILLS[day] if f"{day}{t}" == a)
        p = hd["fills"][a]
        member = hand_pct(pool_values(day), v_a, exclude_self=True)
        if p > 0.5 and not (_close(member, p + (p - 0.5) / (n - 1)) and p < member):
            P.append(f"{day}: the tied fill {a} (p = {p}) does not score below its tied member ({member}) by (p - 1/2) / (n - 1)")
        if not _close(ties["v_cut"][idx[a]], CUTOFF_VALUE[day]):
            P.append(f"{day}: the cutoff member's value {ties['v_cut'][idx[a]]} != {CUTOFF_VALUE[day]}")
        got_ties = int(sum(ties["tie"][idx[f"{day}{t}"]] for t, *_ in FILLS[day]))
        if got_ties != TIES[day]:
            P.append(f"{day}: {got_ties} fills tie at the cutoff, hand count {TIES[day]}")
    if ties["problems"]:
        P += ties["problems"]
    # a tie BELOW one half scores ABOVE the member it ties with (T1's fill at 60.0: 10.5/40 vs 10/39) - the rule is not "a tie always loses"
    g = hand_day("T1")["fills"]["T1G"]
    if not (_close(g, 10.5 / 40) and g > hand_pct(pool_values("T1"), 60.0, exclude_self=True)):
        P.append("T1: the fill tied BELOW one half does not score above its tied member")
    # the stage's own consequence of the rule, on the day with the maximum value shared by more than the cutoff rank: no A+ though every fill is rated
    if any(fl[idx[f"T3{t}"]] == ap.FLAG_APLUS for t in "ABC") or any(fl[idx[f"T3{t}"]] == ap.FLAG_UNRATED for t in "ABC"):
        P.append("T3: a fill at the shared maximum is A+ or unrated")
    return P
