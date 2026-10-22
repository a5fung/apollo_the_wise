"""#705 (b) - the GOLDEN SYNTHETIC FIXTURES of the A+ rating (WOULD-FAIL-IF check 8; data check 4 runs `run_golden()` inside the real read).

Three days, each with its own pool of 40 synthetic fills over the 20 prior sessions (hand-set feature values; the three scales of concept 1
from hand-set daily bars so `wk_ratio` / `pb_ratio` are computed by the REAL formulas), every expectation HAND-COMPUTED from the mid-rank
formula - never from the engine:
  E   the 12th-highest reference score, exactly 3 A+ in fill order and a 4th above-cutoff fill capped; two fill minutes (5 and 200) against
      two PROFILE values of a hand-set linear profile; a zero-volume window (unrated on concept 7); a fill BELOW its D close (a negative
      concept 6 that ranks lowest, never missing) and one with a D close of 0 (missing, unrated); a fill missing concept 5 scored as the mean of
      its six present concepts; a fill with the weekly scale missing carrying 0.5 for it; a grp-missing fill rated under the core and unrated
      under +grp (the two A+ sets differ by it); every direction flipped inverts the A+ set.
  E2  exactly 30 non-missing values on ONE non-5 concept: the reference set is EMPTY and every E2 fill is UNRATED; a 31st value rates.
  E3  the per-scale boundary of concept 1: exactly 30 values on the weekly scale (then on the pullbacks scale) - the fill is ranked on it, every
      reference member carrying it enters 0.5; the fill's score, every member's reference score and the cutoff hand-computed; a 31st value
      ranks the members on it.
The rows carry everything the file-level test needs to write the same population into a synthetic tree (bars, minutes, closes, volumes).
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

import numpy as np

from scripts.probes._cb_backtest import aplus_read as ap

PROFILE = np.asarray([float(f"{m / 390.0:.10f}") for m in range(391)])   # the hand-set profile: PROFILE(m) = m / 390 at the file's %.10f (0 and 1 exact)
CAL_START = dt.date(2023, 1, 2)
N_POOL = 40
E_CI, E2_CI, E3_CI = 150, 250, 350                        # every pool member's stair window ([E - 120, E - 1]) starts inside a file whose first E is session 0


def calendar(n: int = 400, start: dt.date = CAL_START) -> list:
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += dt.timedelta(days=1)
    return out


CAL = calendar()


def set_calendar(start: dt.date) -> list:
    """Rebind the fixture calendar (the file-level tests write the same population into another era's dates)."""
    global CAL
    CAL = calendar(start=start)
    return CAL


@dataclass
class Row:
    ticker: str
    E_ci: int
    fill_minute: int
    tightening_ratio: float
    vol_dry5: float
    rs_best: float
    prior_move: float
    stair_n: "int | None"
    exp_up: "float | None"                               # the intended exp_up_adr (fill = close_D x (1 + exp_up x adr20)); None = close_D 0
    vol_sofar: "float | None"                            # the intended vol_sofar_x (sum v over the window = vol_sofar x adv20 x PROFILE(fm)); None = zero window
    grp_pct: "float | None"
    base_len: int
    wk: "float | None"                                   # the weekly target (bars built to give it); None = fewer than 3 blocks
    pb: "float | None"                                   # the pullback target; None = a single completed pullback (or none)
    eligible: bool = True
    close_d: float = 99.0
    adr20: float = 0.05
    adv20: float = 390.0
    rs_all: float = 50.0
    base_depth: float = 0.1
    atr14_slope: float = 0.8
    range5_adr: float = 0.5
    range_sofar: float = 0.1
    mature: int = 1
    realized_r: float = 0.0
    pnl_adr: float = 0.0
    width_adr: float = 0.5
    stop: float = 90.0
    extra: dict = field(default_factory=dict)

    @property
    def E(self) -> str:
        return CAL[self.E_ci]

    @property
    def D(self) -> str:
        return CAL[self.E_ci - 1]

    @property
    def fill(self) -> float:
        return self.close_d * (1.0 + (self.exp_up or 0.0) * self.adr20)

    @property
    def prof_m(self) -> float:
        return float(PROFILE[self.fill_minute])

    def window_volumes(self) -> list:
        """The volume of every present minute 0..fill_minute-1 (equal shares of the intended sum); the fill minute itself carries 999."""
        if self.vol_sofar is None:
            return [0.0] * self.fill_minute
        total = self.vol_sofar * self.adv20 * self.prof_m
        return [total / self.fill_minute] * self.fill_minute


# ═══ the bars: a pole top P then `base_len` sessions, built so the pinned formulas give the targets ════════════════════════════════
def base_bars(base_len: int, wk, pb, close_d: float = 99.0) -> tuple:
    """(h, l, c) of base_len + 1 rows (index 0 = P, h 100). Swing highs at 5 (99.5) and, when `pb` is set, at 10 (99.6); the first pullback
    dips to 89.5 (depth 10.5 / 100), the second to 99.5 - d2 with d2 = pb x 10.5 x 99.5 / 100 (so pb_ratio = pb); the last 5 sessions' low =
    99 - 10 x wk (so wk_ratio = (10 wk / 99) / (10 / 99) = wk when base_len = 15). `wk` None with base_len < 15 (fewer than 3 blocks); `pb`
    None -> a single swing high after P (one completed pullback)."""
    n = base_len + 1
    h, l, c = np.full(n, 99.0), np.full(n, 98.5), np.full(n, 99.0)
    h[0], l[0] = 100.0, 95.0
    l[1:5] = 89.5
    h[5] = 99.5
    if pb is not None:
        d2 = pb * 10.5 * 99.5 / 100.0
        l[6:10] = 99.5 - d2
        h[10] = 99.6
    if wk is not None:
        if base_len < 15:
            raise ValueError("a weekly target needs 3 blocks (base_len >= 15)")
        l[n - 5:] = 99.0 - 10.0 * wk
        h[n - 5:] = 99.0
    c[-1] = close_d
    return h, l, c


# ═══ the population ═════════════════════════════════════════════════════════════════════════════════════════════════════════════════
def pool_rows(e_ci: int, prefix: str, wk_present: int = 32, pb_present: int = 31, grp_present: int = 36, rs_present: int = 40) -> list:
    """40 pool members over the 20 sessions before `e_ci` (2 per session). Member i: tightening 0.5 + 0.02 i, wk 0.5 + 0.02 i (the first
    `wk_present`), pb 0.4 + 0.02 i (the first `pb_present`), vol_dry5 0.3 + 0.03 i, rs_best 50 + i (the first `rs_present`), prior_move 0.3 +
    0.02 i, stair_n i % 3, exp_up -0.1 + 0.05 i, vol_sofar 0.2 + 0.1 i, grp 10 + 2 i (the first `grp_present`); base_len 15 (12 when both scales
    are absent)."""
    rows = []
    for i in range(N_POOL):
        wk = 0.5 + 0.02 * i if i < wk_present else None
        pb = 0.4 + 0.02 * i if i < pb_present else None
        rows.append(Row(ticker=f"{prefix}{i:02d}", E_ci=e_ci - 20 + i // 2, fill_minute=5, tightening_ratio=0.5 + 0.02 * i, vol_dry5=0.3 + 0.03 * i,
                        rs_best=(50.0 + i) if i < rs_present else None, prior_move=0.3 + 0.02 * i, stair_n=i % 3, exp_up=-0.1 + 0.05 * i,
                        vol_sofar=0.2 + 0.1 * i, grp_pct=(10.0 + 2 * i) if i < grp_present else None,
                        base_len=15 if wk is not None else 12, wk=wk, pb=pb, rs_all=40.0 + i, base_depth=0.1 + 0.01 * i,
                        atr14_slope=0.5 + 0.02 * i, range5_adr=0.5 + 0.01 * i, range_sofar=0.1 + 0.02 * i, realized_r=(-1.0 if i % 4 else 2.0),
                        width_adr=0.3 + 0.01 * i))
    return rows


def day_e_rows() -> list:
    best = dict(tightening_ratio=0.1, vol_dry5=0.1, rs_best=99.0, prior_move=2.0, stair_n=0, exp_up=3.0, vol_sofar=10.0, grp_pct=99.0, base_len=15, wk=0.05, pb=0.05)
    F1 = Row("F1", E_CI, 5, **best, realized_r=12.0, pnl_adr=3.0)
    F3 = Row("F3", E_CI, 6, **dict(best, base_len=12, wk=None, grp_pct=None), realized_r=6.0, pnl_adr=1.0)
    F5 = Row("F5", E_CI, 7, tightening_ratio=1.09, vol_dry5=1.185, rs_best=59.5, prior_move=0.49, stair_n=2, exp_up=0.375, vol_sofar=1.15, grp_pct=61.0,
             base_len=14, wk=None, pb=None, realized_r=-1.0)
    F6 = Row("F6", E_CI, 8, **best, close_d=0.0)                                       # concept 6 missing: unrated (in-memory only)
    F7 = Row("F7", E_CI, 9, **dict(best, vol_sofar=None))                              # a zero-volume window: unrated on concept 7
    F2 = Row("F2", E_CI, 200, **dict(best, rs_best=69.5, stair_n=None), adv20=39.0, realized_r=11.0, pnl_adr=2.0)
    F4 = Row("F4", E_CI, 300, **dict(best, exp_up=-2.0), realized_r=1.0)
    return [F1, F3, F5, F6, F7, F2, F4]


def day_e2_rows(rs_present: int = 30) -> list:
    return pool_rows(E2_CI, "Q", rs_present=rs_present) + [Row("F8", E2_CI, 5, **dict(tightening_ratio=0.1, vol_dry5=0.1, rs_best=99.0, prior_move=2.0,
                                                                                         stair_n=0, exp_up=3.0, vol_sofar=10.0, grp_pct=99.0, base_len=15, wk=0.05, pb=0.05))]


def day_e3_rows(scale: str = "weekly", present: int = 30) -> list:
    if scale == "weekly":
        pool = pool_rows(E3_CI, "R", wk_present=present, pb_present=40, grp_present=40)
    else:
        pool = pool_rows(E3_CI, "R", wk_present=40, pb_present=present, grp_present=40)
    return pool + [Row("F9", E3_CI, 5, tightening_ratio=0.75, vol_dry5=0.75, rs_best=75.0, prior_move=0.75, stair_n=1, exp_up=0.75, vol_sofar=1.95, grp_pct=55.0,
                       base_len=15, wk=0.75, pb=0.75)]


def golden_rows(e2_rs: int = 30, e3_scale: str = "weekly", e3_present: int = 30, with_f6: bool = True) -> list:
    rows = pool_rows(E_CI, "P") + day_e_rows() + day_e2_rows(e2_rs) + day_e3_rows(e3_scale, e3_present)
    if not with_f6:
        rows = [r for r in rows if r.ticker != "F6"]
    rows.sort(key=lambda r: (r.E_ci, r.fill_minute, r.ticker))
    return rows


def features_of(r: Row) -> dict:
    """The row's features as the engine reads them: the two scales from the REAL formulas over the hand-set bars."""
    h, l, c = base_bars(r.base_len, r.wk, r.pb, r.close_d)
    wk, pb = ap.wk_ratio_of(h, l, c, r.base_len), ap.pb_ratio_of(h, l)
    vols = r.window_volumes()
    sumv = float(sum(vols))
    return {"tightening_ratio": r.tightening_ratio, "wk_ratio": wk, "pb_ratio": pb, "vol_dry5": r.vol_dry5, "rs_best": r.rs_best, "prior_move": r.prior_move,
            "stair_n": r.stair_n, "exp_up_adr": ap.exp_up_adr_of(r.fill, r.close_d, r.adr20), "vol_sofar_x": ap.vol_sofar_of(sumv, r.adv20, r.prof_m),
            "grp_pct": r.grp_pct, "base_len": r.base_len, "range5_adr": r.range5_adr, "base_depth": r.base_depth, "atr14_slope": r.atr14_slope,
            "rs_all": r.rs_all, "range_sofar_adr": r.range_sofar}


def cols_of(rows: list) -> dict:
    """The engine's input for `rows` (in fill order)."""
    cols = {k: [] for k in ("ticker", "D", "E", "K", "fill", "fill_minute", "fill_month", "adr20", "width_adr", "stop", "mature", "open_mark", "early_close",
                            "phase_qqq_10_20", "eligible", "E_ci", "D_ci", "week", "weekday", "rs_best")}
    feats = {k: [] for k in ("tightening_ratio", "wk_ratio", "pb_ratio", "vol_dry5", "prior_move", "stair_n", "exp_up_adr", "vol_sofar_x", "grp_pct", "base_len",
                             "range5_adr", "base_depth", "atr14_slope", "rs_all", "range_sofar_adr")}
    for r in rows:
        f = features_of(r)
        cols["ticker"].append(r.ticker)
        cols["D"].append(r.D)
        cols["E"].append(r.E)
        cols["K"].append("tl")
        cols["fill"].append(r.fill)
        cols["fill_minute"].append(r.fill_minute)
        cols["fill_month"].append(r.E[:7])
        cols["adr20"].append(r.adr20)
        cols["width_adr"].append(r.width_adr)
        cols["stop"].append(r.stop)
        cols["mature"].append(r.mature)
        cols["open_mark"].append(0)
        cols["early_close"].append(0)
        cols["phase_qqq_10_20"].append(1)
        cols["eligible"].append(r.eligible)
        cols["E_ci"].append(r.E_ci)
        cols["D_ci"].append(r.E_ci - 1)
        cols["week"].append(ap.iso_week(r.E))
        cols["weekday"].append(dt.date.fromisoformat(r.E).weekday())
        cols["rs_best"].append(f["rs_best"])
        for k in feats:
            feats[k].append(f[k])
    cols.update(feats)
    return cols


# ═══ the hand computation (closed form from the mid-rank formula; never the engine) ═════════════════════════════════════════════════
def _pct(values: list, x, higher: bool, exclude_self: bool = False):
    """(worse + 0.5 equal) / |S| for x against the non-missing `values` (x itself removed once when `exclude_self`)."""
    if x is None:
        return None
    S = [v for v in values if v is not None]
    if exclude_self:
        S.remove(x)
    if len(S) < ap.POOL_FLOOR:
        return None
    worse = sum(1 for v in S if (v < x if higher else v > x))
    eq = sum(1 for v in S if v == x)
    return (worse + 0.5 * eq) / len(S)


HIGHER = {"tightening_ratio": False, "wk_ratio": False, "pb_ratio": False, "vol_dry5": False, "rs_best": True, "prior_move": True, "stair_n": False,
          "exp_up_adr": True, "vol_sofar_x": True, "grp_pct": True}


def hand_score(fill_feats: dict, pool_feats: list, spec: str = "core", exclude_self: bool = False, flip: bool = False):
    """The hand score of a fill against a pool ({feature: [values]}): the mean of the present concepts' percentiles, concept 1 = the mean of its
    three scales (a missing scale 0.5), concept 5 optional, +grp an eighth required concept; `flip` reads every percentile as 1 - pct."""
    def p(k):
        v = _pct(pool_feats[k], fill_feats[k], HIGHER[k], exclude_self)
        return None if v is None else (1 - v if flip else v)
    daily, wk, pb = p("tightening_ratio"), p("wk_ratio"), p("pb_ratio")
    if daily is None:
        return None
    c1 = (daily + (0.5 if wk is None else wk) + (0.5 if pb is None else pb)) / 3
    parts = [c1]
    for k in ("vol_dry5", "rs_best", "prior_move", "exp_up_adr", "vol_sofar_x"):
        v = p(k)
        if v is None:
            return None
        parts.append(v)
    if spec == "grp":
        v = p("grp_pct")
        if v is None:
            return None
        parts.append(v)
    c5 = p("stair_n")
    if c5 is not None:
        parts.append(c5)
    return sum(parts) / len(parts)


def hand_day(rows: list, e_ci: int, spec: str = "core", flip: bool = False) -> dict:
    """{"cutoff": the 12th-highest reference score, "ref": {ticker: score}, "fills": {ticker: score}} for the fills on `e_ci` by hand."""
    pool = [r for r in rows if e_ci - 20 <= r.E_ci <= e_ci - 1]
    fills = [r for r in rows if r.E_ci == e_ci]
    pf = {r.ticker: features_of(r) for r in pool + fills}
    pool_feats = {k: [pf[r.ticker][k] for r in pool] for k in HIGHER}
    ref = {r.ticker: hand_score(pf[r.ticker], pool_feats, spec, exclude_self=True, flip=flip) for r in pool}
    rated = sorted((v for v in ref.values() if v is not None), reverse=True)
    cutoff = rated[ap.CUTOFF_RANK[3] - 1] if len(rated) >= ap.CUTOFF_RANK[3] else None
    return {"cutoff": cutoff, "ref": ref, "fills": {r.ticker: hand_score(pf[r.ticker], pool_feats, spec, flip=flip) for r in fills}, "pool_n": len(pool)}


def _close(a, b, tol=1e-12) -> bool:
    if a is None or b is None or (isinstance(a, float) and a != a) or (isinstance(b, float) and b != b):
        return (a is None or a != a) and (b is None or b != b)
    return abs(float(a) - float(b)) <= tol


def flipped_features() -> dict:
    return {k: (col, -d) for k, (col, d) in ap.FEATURES.items()}


def run_golden() -> list:
    """Every golden expectation against the engine; returns the problems (empty = check 8 / data check 4 pass)."""
    P = []
    rows = golden_rows()
    cols = cols_of(rows)
    res = ap.rate_population(cols)
    idx = {t: i for i, t in enumerate(cols["ticker"])}
    f = lambda t, s="core", N=3: res["flag"][(s, N)][idx[t]]       # noqa: E731
    sc = lambda t, s="core": res["score"][s][idx[t]]               # noqa: E731
    cut = lambda t, s="core", N=3: res["cutoff"][(s, N)][idx[t]]   # noqa: E731
    # ── day E ──
    hd = hand_day(rows, E_CI)
    if not _close(cut("F1"), hd["cutoff"]):
        P.append(f"E: the cutoff {cut('F1')} is not the hand-computed 12th-highest reference score {hd['cutoff']}")
    for t, want in hd["fills"].items():
        if not _close(sc(t), want):
            P.append(f"E: {t}'s core score {sc(t)} != hand {want}")
    want_flags = {"F1": "aplus", "F3": "aplus", "F5": "rest", "F6": "unrated", "F7": "unrated", "F2": "aplus", "F4": "capped"}
    got = {t: f(t) for t in want_flags}
    if got != want_flags:
        P.append(f"E: flags {got} != {want_flags} (3 A+ in fill order, the 4th above-cutoff fill capped)")
    fe = {t: features_of(r) for t, r in ((r.ticker, r) for r in rows)}
    r1, r2 = next(r for r in rows if r.ticker == "F1"), next(r for r in rows if r.ticker == "F2")
    if not (r1.prof_m == PROFILE[5] != PROFILE[200] == r2.prof_m and abs(fe["F1"]["vol_sofar_x"] - 10) < 1e-9 and abs(fe["F2"]["vol_sofar_x"] - 10) < 1e-9):
        P.append("E: vol_sofar_x at fill minutes 5 and 200 against PROFILE(5) / PROFILE(200) is not 10 for both")
    if fe["F7"]["vol_sofar_x"] is not None or fe["F6"]["exp_up_adr"] is not None:
        P.append("E: the zero-volume window / the D close of 0 are not missing")
    if not (fe["F4"]["exp_up_adr"] < 0 and res["pct"][idx["F4"], ap.KEY_IDX["c6"]] == 0.0):
        P.append("E: the fill below its D close does not rank lowest on concept 6")
    # concept 5 missing -> the mean of the six present concepts (never 0): F2's hand score counts six parts
    six = hand_score(fe["F2"], {k: [fe[r.ticker][k] for r in rows if E_CI - 20 <= r.E_ci <= E_CI - 1] for k in HIGHER})
    if not _close(sc("F2"), six) or fe["F2"]["stair_n"] is not None or abs(six - (5 + 0.5) / 6) > 1e-12:
        P.append(f"E: F2 (concept 5 missing) scores {sc('F2')}, not the mean of its six present concepts {six}")
    # a missing SCALE carries 0.5: F3's concept-1 percentile = (1 + 0.5 + 1) / 3
    pct3 = res["pct"][idx["F3"]]
    c1_3 = (pct3[ap.KEY_IDX["c1_daily"]] + 0.5 + pct3[ap.KEY_IDX["c1_pb"]]) / 3
    others = sum(pct3[ap.KEY_IDX[k]] for k in ("c2", "c3", "c4", "c5", "c6", "c7"))     # c5 = 0.825 (stair 0 against 14 equal / 26 worse)
    if fe["F3"]["wk_ratio"] is not None or not _close(sc("F3"), (c1_3 + others) / 7) or abs(c1_3 - 2.5 / 3) > 1e-12 or abs(others - 5.825) > 1e-12:
        P.append(f"E: F3's missing weekly scale does not carry 0.5 (score {sc('F3')})")
    # +grp: F3 (grp missing) rated under the core and unrated under +grp; the two A+ sets differ by it
    core_set, grp_set = ap.aplus_set(cols, res, "core", 3), ap.aplus_set(cols, res, "grp", 3)
    hg = hand_day(rows, E_CI, "grp")
    if f("F3", "grp") != "unrated" or ("F3", CAL[E_CI]) not in core_set or ("F3", CAL[E_CI]) in grp_set:
        P.append("E: the grp-missing fill is not rated under the core and unrated under +grp")
    if not _close(cut("F1", "grp"), hg["cutoff"]) or any(not _close(sc(t, "grp"), v) for t, v in hg["fills"].items()):
        P.append("E: the +grp scores / cutoff differ from the hand computation")
    if {t for t, e in grp_set if e == CAL[E_CI]} != {"F1", "F2", "F4"}:
        P.append(f"E: the +grp A+ set on E is {sorted(t for t, e in grp_set if e == CAL[E_CI])}, not F1 / F2 / F4")
    # every direction flipped inverts the A+ set: the rest fill is the only A+; every former A+ is below the flipped cutoff
    resf = ap.rate_population(cols, features=flipped_features())
    hf = hand_day(rows, E_CI, flip=True)
    flipped = {t for t, e in ap.aplus_set(cols, resf, "core", 3) if e == CAL[E_CI]}
    if flipped != {"F5"} or not _close(resf["cutoff"][("core", 3)][idx["F5"]], hf["cutoff"]):
        P.append(f"E: with every direction flipped the A+ set is {sorted(flipped)}, not F5 alone (cutoff {resf['cutoff'][('core', 3)][idx['F5']]} vs hand {hf['cutoff']})")
    for t in ("F1", "F2", "F3", "F4"):
        if resf["flag"][("core", 3)][idx[t]] != "rest":
            P.append(f"E: flipped, {t} reads {resf['flag'][('core', 3)][idx[t]]}, not rest")
    # ── day E2: the empty reference set ──
    if f("F8") != "unrated" or not np.isnan(cut("F8")):
        P.append(f"E2: F8 reads {f('F8')} with cutoff {cut('F8')} - the reference set should be EMPTY (30 values on rs_best: every member sees 29)")
    rows31 = golden_rows(e2_rs=31)
    cols31 = cols_of(rows31)
    res31 = ap.rate_population(cols31)
    i8 = cols31["ticker"].index("F8")
    if res31["flag"][("core", 3)][i8] != "aplus" or np.isnan(res31["cutoff"][("core", 3)][i8]):
        P.append("E2: with a 31st rs_best value F8 is not rated")
    h31 = hand_day(rows31, E2_CI)
    if not _close(res31["cutoff"][("core", 3)][i8], h31["cutoff"]):
        P.append("E2: the 31-value cutoff differs from the hand computation")
    # ── day E3: the per-scale boundary, weekly then pullbacks ──
    for scale in ("weekly", "pullbacks"):
        rows3 = golden_rows(e3_scale=scale, e3_present=30)
        cols3 = cols_of(rows3)
        res3 = ap.rate_population(cols3)
        i9 = cols3["ticker"].index("F9")
        h3 = hand_day(rows3, E3_CI)
        key = ap.KEY_IDX["c1_wk" if scale == "weekly" else "c1_pb"]
        if np.isnan(res3["pct"][i9, key]):
            P.append(f"E3 ({scale}): F9 is not ranked on the scale with |S| = 30")
        pool = np.flatnonzero((np.asarray(cols3["E_ci"]) >= E3_CI - 20) & (np.asarray(cols3["E_ci"]) <= E3_CI - 1))
        rd = ap.rate_day(ap.oriented_matrix(cols3), pool, np.array([i9]), ap.SPECS, ap.SPEC_NS)
        if not np.isnan(rd["ref"][:, key]).all():
            P.append(f"E3 ({scale}): a reference member is ranked on the scale (it should see 29 and enter 0.5)")
        for k, j in enumerate(pool):
            if not _close(rd["ref_score"]["core"][k], h3["ref"][cols3["ticker"][j]]):
                P.append(f"E3 ({scale}): member {cols3['ticker'][j]}'s reference score {rd['ref_score']['core'][k]} != hand {h3['ref'][cols3['ticker'][j]]}")
                break
        if not _close(res3["score"]["core"][i9], h3["fills"]["F9"]) or not _close(res3["cutoff"][("core", 3)][i9], h3["cutoff"]):
            P.append(f"E3 ({scale}): F9's score / the cutoff differ from the hand computation")
        rows31 = golden_rows(e3_scale=scale, e3_present=31)
        cols31 = cols_of(rows31)
        pool31 = np.flatnonzero((np.asarray(cols31["E_ci"]) >= E3_CI - 20) & (np.asarray(cols31["E_ci"]) <= E3_CI - 1))
        rd31 = ap.rate_day(ap.oriented_matrix(cols31), pool31, np.array([cols31["ticker"].index("F9")]), ap.SPECS, ap.SPEC_NS)
        if int((~np.isnan(rd31["ref"][:, key])).sum()) != 31:
            P.append(f"E3 ({scale}): with a 31st value the members are not ranked on the scale")
        h31 = hand_day(rows31, E3_CI)
        if not _close(rd31["cutoff"][("core", 3)], h31["cutoff"]):
            P.append(f"E3 ({scale}): the 31-value cutoff differs from the hand computation")
    return P
