"""#705 (c) - RS leadership ALONE, the one read on the sealed 2025-26 (docs/analysis/cb_rs_alone_prereg_2026-10-22.md) on the registered-read
scaffold. BUILT ON SYNTHETIC DATA; the build computed no real outcome (`--dry-run [--self-check]` and `--print-pins` read FEATURE columns only).

Stage (dispatched by runner.py):
  rs-alone-read --period holdout     the parent's `alone_c3` row (the best of the 1-/3-/6-month return percentiles, `rs_best`, on its own), N = 3, on
                                     the sealed 2025-26 population pooled as the parent pools it (the trailing 2022-24 fills pool the first weeks).
                                     The freeze, the precondition (both parent verdicts exist, the consequence reads NOT RECORDED, the next registration
                                     is `alone_c3`), STEP 0 (equality targets before any outcome column), the look-ahead / later-fill / counts / pool /
                                     shuffle checks, the golden tie fixtures, the outcomes (read, never re-walked), the bar + the paired veto, the
                                     independent re-derivation (VERDICT MATCH before the verdict is written), the verdict files and the consequence line.
                                     `--dry-run` = STEP 0 only; `--dry-run --self-check` adds the rating counts, every feature-only check and the
                                     re-derivation's A+ SET / scores / cutoffs (no outcome column is opened by either).

ONE score is computed on 2025-26: every other feature column is padded with None, so `rate_population` (the parent's engine, imported - not
copied) can only fill the `rs_best` percentile. The stage opens: the holdout and discovery exitpb tables (FEATURE columns), `candidates.tsv`
(`rs_best` only) and the SPY dates of the daily export (the session calendar). It writes NO `aplus_*holdout*` artefact: its own names are
`trades_holdout_rs_alone.tsv.gz` (+ `.partial`), `rs_alone_verdict_holdout.{json,txt}`, `rs_alone_report_holdout.{tsv,txt}`.

Every helper of the runner is reached through `ctx.rt`; this module imports no runner code (the runner imports it to register the read).
"""
from __future__ import annotations

import datetime as dt
import sys
import time
import zlib
from collections import Counter
from pathlib import Path

import numpy as np

from scripts.probes._cb_backtest import aplus_read as ap
from scripts.probes._cb_backtest import registered_read as rr

# ═════════════════════════════════════════════════════════════════════════════════════════════
# the registration's constants (every number is the doc's)
# ═════════════════════════════════════════════════════════════════════════════════════════════
RS_DOC = "cb_rs_alone_prereg_2026-10-22.md"
RS_TAG = "rs_alone"                                       # trades_<period>_rs_alone.tsv.gz, rs_alone_verdict_<period>.*, rs_alone_report_<period>.*
RS_PERIODS = ("holdout",)
RS_SPEC = "alone_c3"                                      # the parent's row: concept 3 (RS leadership) alone
RS_N = ap.N_DECIDES                                       # N = 3 decides; no N = 1 / 5 row
RS_NEXT = "alone_c3"                                      # what `next_registration()` must return for this read to run
RS_SPECS = {RS_SPEC: ap.SPECS[RS_SPEC]}
RS_NS = {RS_SPEC: (RS_N,)}
RS_COLUMN = "rs_best"
RS_CAND_COLS = ["ticker", "D", "E", "K", "split", "rs_best"]      # the ONLY candidates columns the run reads (no other feature, no E-day column)
# the five pinned holdout counts (STEP 0 equality targets): the parent's `APLUS_EXPECTED["holdout"]`, restated and asserted equal below
RS_EXPECTED = {"joined": 7570, "fills": 7547, "open": 39, "weeks": 93, "dropped": 23}
if any(ap.APLUS_EXPECTED["holdout"][k] != v for k, v in RS_EXPECTED.items()):
    raise ImportError("rs_alone_read: the five pinned holdout counts differ from aplus_read.APLUS_EXPECTED['holdout'] - the two registrations disagree")
RS_MATURE_NOTE = 7508                                     # 7,547 fills - 39 open marks, printed against the census (the doc's "7,508 mature")
# every FEATURE column the engine reads, minus the one this read scores: padded with None on 2025-26 ("every other score is NOT computed")
FEATURE_COLUMNS = tuple(dict.fromkeys(c for c, _d in ap.FEATURES.values()))
NOT_COMPUTED = tuple(c for c in FEATURE_COLUMNS if c != RS_COLUMN)
CHECK4C_SAMPLE = ap.CHECK1_SAMPLE                         # 50 sampled fills + every A+ fill (parent check 1 (c))
TOP_SHARE = 0.04                                          # the doc's "top 4% of fills" census


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the precondition (spec check 2) - a refusal exits 3 and writes nothing
# ═════════════════════════════════════════════════════════════════════════════════════════════
def _fail(*lines) -> None:
    for ln in lines:
        print(ln, file=sys.stderr)
    raise SystemExit(3)


def precondition(ctx: rr.Ctx) -> dict:
    """Both parent verdict JSONs exist, `consequence()` reads NOT RECORDED and `next_registration()` returns `alone_c3` - the registered rule that
    NAMED this read. Also refuses when any `aplus_*holdout*` artefact is on disk: the sealed era was read for the A+ rating (aplus-confirm ran), which
    the NOT RECORDED cell makes impossible - a state the registration does not describe. Returns the facts the report prints."""
    v = ap.load_verdicts(ctx)
    if isinstance(v, str):
        _fail(f"REFUSED: the RS-alone read runs only after the A+ rating's two deciding verdicts are on file: {v}")
    cell = ap.consequence(v["pre"], v["discovery"])
    if cell["cell"] != "NOT RECORDED":
        _fail(f"REFUSED: the A+ rating's consequence cell reads {cell['cell']} ({cell['why']}) - this read runs only on NOT RECORDED")
    rows3 = {k: {s.split("|")[0]: r for s, r in v[k].get("rows", {}).items() if s.endswith(f"|{ap.N_DECIDES}")} for k in ("pre", "discovery")}
    nxt = ap.next_registration(rows3["pre"], rows3["discovery"])
    if nxt != RS_NEXT:
        _fail(f"REFUSED: the A+ rating's registered next registration is {nxt!r}, not {RS_NEXT!r} - this read is not the one the rule named")
    stray = ap.holdout_artefacts(ctx)
    if stray:
        _fail(f"REFUSED: {stray[0]} exists - an A+ artefact of the sealed era is on disk, which a NOT RECORDED rating cannot have produced; the operator "
              f"inspects it first")
    return {"cell": cell["cell"], "why": cell["why"], "next_registration": nxt, "pre": v["pre"]["verdict"], "discovery": v["discovery"]["verdict"],
            "pre_paired": v["pre"]["paired"]["reading"], "discovery_paired": v["discovery"]["paired"]["reading"]}


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the readers: candidates (rs_best only) and the SPY session calendar
# ═════════════════════════════════════════════════════════════════════════════════════════════
def read_rs_cands(path, label_of, extra: tuple = ()):
    """The candidates file's tl rows by `RS_CAND_COLS` - `rs_best` and the keys, nothing else. THE LABEL IS NOT TRUSTED: every row's `split` must equal
    `label_of(D)`, else ValueError (the parent's rule). `extra`: columns read ONLY by check 4 (b)'s shuffled rebuild."""
    c = ap.read_table(path, list(dict.fromkeys(list(RS_CAND_COLS) + list(extra))))
    bad = [(t, d, s) for t, d, s in c[["ticker", "D", "split"]].itertuples(index=False) if s != label_of(d)]
    if bad:
        t, d, s = bad[0]
        raise ValueError(f"{path}: row {t} D={d} is labelled split={s!r}, not {label_of(d)!r}: this is not the period's file - refusing to read it")
    return c[c["K"] == ap.POP_K].reset_index(drop=True)


_CAL_SLOT: dict = {}


def calendar_cached(path) -> tuple:
    """(cal, cal_ci): the SPY session dates of the daily export, sorted, and date -> index. ONLY the ticker and date columns are read (chunked), so
    no price or volume of any row can reach the rating. One slot keyed by (path, size, mtime)."""
    p = Path(path).resolve()
    st = p.stat()
    key = (str(p), st.st_size, st.st_mtime_ns)
    if _CAL_SLOT.get("key") == key:
        return _CAL_SLOT["value"]
    pd = ap._pd()
    dates = []
    for df in pd.read_csv(p, header=None, usecols=[0, 1], names=["ticker", "d"], dtype=str, keep_default_na=False, chunksize=2_000_000):
        dates += df.loc[df["ticker"] == "SPY", "d"].tolist()
    if not dates:
        raise ValueError(f"{p}: no SPY rows - no session calendar")
    cal = sorted(dates)
    if len(set(cal)) != len(cal):
        raise ValueError(f"{p}: SPY carries a date twice - no session calendar")
    value = (cal, {d: k for k, d in enumerate(cal)})
    _CAL_SLOT.clear()
    _CAL_SLOT.update(key=key, value=value)
    return value


def clear_calendar_cache() -> None:
    _CAL_SLOT.clear()


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the inputs: prepare (the pinned tables, feature columns only) and the feature build
# ═════════════════════════════════════════════════════════════════════════════════════════════
def rs_prepare(ctx: rr.Ctx) -> dict:
    """The sealed population exactly as the parent's `aplus_prepare` builds it for the holdout (its readers, its edge rule, its pool-only rows),
    minus every input this score does not read. Opens no outcome column, no daily bar, no minute row. The precondition runs here."""
    pre = precondition(ctx)
    pd = ap._pd()
    paths = ap.period_paths(ctx, "holdout")
    fills, n_joined, in_era = ap.read_fills(paths["fills"], "holdout")
    fills["eligible"] = in_era
    n_dropped = int((~in_era).sum())
    pool_only, _n, _m = ap.read_fills(paths["pool_fills"], "discovery")
    first_e = fills.loc[fills["eligible"], "E"].min()
    cutoff = (ap._isodate(first_e) - dt.timedelta(days=45)).isoformat()
    pool_only = pool_only[pool_only["E"] >= cutoff].copy()
    pool_only["eligible"] = False
    both = set(zip(fills["ticker"], fills["D"], fills["E"], fills["K"])) & set(zip(pool_only["ticker"], pool_only["D"], pool_only["E"], pool_only["K"]))
    if both:
        raise ValueError(f"{paths['fills']} and {paths['pool_fills']}: {len(both)} fills in BOTH tables (first {sorted(both)[0]}) - the per-split tables "
                         f"overlap; refusing to read them")
    fills = pd.concat([pool_only, fills], ignore_index=True).sort_values(["E", "fill_minute", "ticker"]).reset_index(drop=True)
    rt = ctx.rt
    label_of = lambda d: rt.split_label(ap._isodate(d))                    # noqa: E731
    cands = read_rs_cands(paths["cands"], label_of)
    rows = [{"ticker": t, "E": e, "K": ap.POP_K, "D": d} for (t, d, e), ok in zip(fills[["ticker", "D", "E"]].itertuples(index=False), fills["eligible"]) if ok]
    opens = (paths["fills"], paths["pool_fills"], paths["export"])
    return {"rows": rows, "inp": None, "path": paths["cands"], "opens": opens, "fills": fills, "cands": cands, "paths": paths, "n_joined": n_joined,
            "n_dropped": n_dropped, "period": "holdout", "label_of": label_of, "precondition": pre}


def engine_cols(base: dict, rs_best: list) -> dict:
    """The engine's input: `base` (identity, order and week columns) + `rs_best` + every OTHER feature column padded with None. The padding is the
    structural statement that no other score is computed: a None column ranks nothing (|S| = 0 < the pool floor)."""
    n = len(rs_best)
    cols = dict(base)
    cols[RS_COLUMN] = list(rs_best)
    for c in NOT_COMPUTED:
        cols[c] = [None] * n
    return cols


def build_cols(ctx: rr.Ctx, prep: dict) -> dict:
    """Every row of the frame (eligible and pool-only) in fill order: the fills' identity columns, the calendar index of E and D, the ISO week, and
    `rs_best` from the candidates by (ticker, D, E, K). Returns {"cols", "problems", "cal"}."""
    fills, cands, paths = prep["fills"], prep["cands"], prep["paths"]
    cal, cal_ci = calendar_cached(paths["export"])
    n = len(fills)
    base = {k: list(fills[k]) for k in ("ticker", "D", "E", "K", "fill", "fill_minute", "fill_month", "adr20", "width_adr", "stop", "mature", "open_mark",
                                        "early_close", "eligible")}
    base["fill_minute"] = [int(x) for x in base["fill_minute"]]
    base["E_ci"] = [cal_ci.get(e, -1) for e in base["E"]]
    base["D_ci"] = [cal_ci.get(d, -1) for d in base["D"]]
    base["week"] = [ap.iso_week(e) for e in base["E"]]
    base["weekday"] = [ap._isodate(e).weekday() for e in base["E"]]
    problems = []
    ck = {}
    for rec in cands[["ticker", "D", "E", "K", RS_COLUMN]].itertuples(index=False):
        key = (rec.ticker, rec.D, rec.E, rec.K)
        if key in ck:
            problems.append(f"candidates: two rows for {key}")
        ck[key] = rec
    rs = [None] * n
    for i in range(n):
        key = (base["ticker"][i], base["D"][i], base["E"][i], base["K"][i])
        rec = ck.get(key)
        if rec is None:
            problems.append(f"candidates: no row for {key}")
            continue
        rs[i] = ap._f(getattr(rec, RS_COLUMN))
    return {"cols": engine_cols(base, rs), "problems": problems, "cal": cal}


def rate_alone(cols: dict) -> dict:
    """The parent's engine on ONE spec: `rate_population` with `alone_c3` at N = 3 (the 12th-highest reference score is the cutoff, the weekly cap in
    fill order, the pool of the prior 20 sessions, floor 30)."""
    return ap.rate_population(cols, RS_SPECS, RS_NS)


def flags(res: dict) -> np.ndarray:
    return res["flag"][(RS_SPEC, RS_N)]


# ═════════════════════════════════════════════════════════════════════════════════════════════
# STEP 0 - the census (features only), its equality targets, the rating counts, the ties at the cutoff
# ═════════════════════════════════════════════════════════════════════════════════════════════
def _rs_array(cols: dict) -> np.ndarray:
    return np.asarray([np.nan if x is None else float(x) for x in cols[RS_COLUMN]], dtype=float)


def ties_at_cutoff(cols: dict, res: dict) -> dict:
    """Per eligible E date: the VALUE of the cutoff member (the pool member whose leave-one-out reference score is the 12th highest) - read from
    the pool's `rs_best` values directly: the reference score is strictly increasing in the value, so the 12th-highest score belongs to the
    12th-highest value - and cross-checked against the engine's own cutoff (the reference score recomputed for that value must equal it). A fill TIES at
    the cutoff when its `rs_best` equals that value. Returns {"tie": bool per row, "v_cut": per row, "problems": [...]}."""
    E_ci = np.asarray(cols["E_ci"], dtype=np.int64)
    n = len(E_ci)
    order = np.argsort(E_ci, kind="stable")
    Es = E_ci[order]
    rs = _rs_array(cols)
    el = np.asarray(cols["eligible"], dtype=bool)
    cut = res["cutoff"][(RS_SPEC, RS_N)]
    out = {"tie": np.zeros(n, dtype=bool), "v_cut": np.full(n, np.nan), "problems": []}
    rank = ap.CUTOFF_RANK[RS_N]
    for e in np.unique(E_ci[el]):
        day = np.flatnonzero(E_ci == e)
        pool = order[np.searchsorted(Es, e - ap.POOL_SESSIONS, side="left"):np.searchsorted(Es, e - 1, side="right")]
        P = rs[pool]
        P = P[~np.isnan(P)]
        nS = len(P)
        engine = float(cut[day[0]])
        if nS - 1 < ap.POOL_FLOOR or nS < rank:
            if engine == engine:
                out["problems"].append(f"ties: E-index {int(e)} has no cutoff by the pool values but the engine's cutoff is {engine}")
            continue
        v = float(np.sort(P)[::-1][rank - 1])
        ref = (int((P < v).sum()) + 0.5 * (int((P == v).sum()) - 1)) / (nS - 1)
        if not (engine == engine and abs(engine - ref) <= 1e-12):
            out["problems"].append(f"ties: E-index {int(e)}: the cutoff member's reference score {ref!r} is not the engine's cutoff {engine!r}")
            continue
        out["v_cut"][day] = v
        out["tie"][day] = rs[day] == v
    return out


def rs_census(cols: dict) -> dict:
    """The `rs_best` census over the ELIGIBLE rows (features only): present / missing, distinct values, the quantiles, the share at 100.0 and the top 4%
    of fills (those at or above the 4th-percentile line: how many distinct values they hold)."""
    el = np.flatnonzero(np.asarray(cols["eligible"], dtype=bool))
    rs = _rs_array(cols)[el]
    ok = rs[~np.isnan(rs)]
    c = {"rs_present": int(len(ok)), "rs_missing": int(np.isnan(rs).sum()), "rs_distinct": int(len(np.unique(ok)))}
    if len(ok):
        srt = np.sort(ok)[::-1]
        k = max(1, int(np.ceil(TOP_SHARE * len(ok))))
        top = ok[ok >= srt[k - 1]]
        c.update(rs_min=float(ok.min()), rs_q1=float(np.quantile(ok, 0.25)), rs_median=float(np.median(ok)), rs_q3=float(np.quantile(ok, 0.75)),
                 rs_max=float(ok.max()), rs_at_100=int((ok >= 100.0).sum()), rs_top_n=int(len(top)), rs_top_distinct=int(len(np.unique(top))),
                 rs_top_low=float(top.min()), rs_top_high=float(top.max()))
    return c


def rs_census_text(c: dict) -> str:
    if not c["rs_present"]:
        return "  rs_best: none present"
    return (f"  rs_best census (eligible fills): present {c['rs_present']:,}, missing {c['rs_missing']}, distinct values {c['rs_distinct']:,}; min {c['rs_min']:.1f} "
            f"q1 {c['rs_q1']:.1f} median {c['rs_median']:.1f} q3 {c['rs_q3']:.1f} max {c['rs_max']:.1f}; at 100.0: {c['rs_at_100']} "
            f"({100 * c['rs_at_100'] / c['rs_present']:.2f}%); the top 4% of fills ({c['rs_top_n']}) hold {c['rs_top_distinct']} distinct values "
            f"({c['rs_top_high']:.1f} down to {c['rs_top_low']:.1f})")


def census(cols: dict, prep: dict, res: dict, ties: dict) -> dict:
    """The STEP 0 census over the eligible rows: the five pinned counts, the `rs_best` census, the rating counts and the ties at the cutoff."""
    el = np.asarray(cols["eligible"], dtype=bool)
    fl = flags(res)
    weeks = np.asarray(cols["week"], dtype=object)
    idx = np.flatnonzero(el)
    pool_n = res["pool_n"]
    c = {"joined": int(prep["n_joined"]), "fills": int(len(idx)), "open": int(sum(int(cols["open_mark"][i]) for i in idx)), "weeks": len({cols["week"][i] for i in idx}),
         "dropped": int(prep["n_dropped"]), "mature": int(sum(int(cols["mature"][i]) for i in idx)), "pool_only": int((~el).sum()),
         "thin": int((pool_n[idx] < ap.POOL_FLOOR).sum()), "pool_min": int(pool_n[idx].min()) if len(idx) else None,
         "pool_median": float(np.median(pool_n[idx])) if len(idx) else None,
         "aplus": int(((fl == ap.FLAG_APLUS) & el).sum()), "capped": int(((fl == ap.FLAG_CAPPED) & el).sum()), "rest": int(((fl == ap.FLAG_REST) & el).sum()),
         "unrated": int(((fl == ap.FLAG_UNRATED) & el).sum())}
    c["rated"] = c["aplus"] + c["capped"] + c["rest"]
    after = sorted(set(weeks[el]))[ap.BURN_IN_WEEKS:]
    cnt = Counter(weeks[(fl == ap.FLAG_APLUS) & el])
    c["weeks_under_3_share"] = (sum(1 for w in after if cnt[w] < RS_N) / len(after)) if after else None
    c["ties_at_cutoff"] = int((ties["tie"] & el).sum())
    c["ties_flagged_rest"] = int((ties["tie"] & el & (fl == ap.FLAG_REST)).sum())
    c["ties_flagged_aplus"] = int((ties["tie"] & el & (fl == ap.FLAG_APLUS)).sum())
    c.update(rs_census(cols))
    return c


def census_text(c: dict) -> list:
    lo, hi = ap.EXPECT_APLUS_N["holdout"]
    return [f"STEP 0 (holdout, features only, no outcome column opened): joined {c['joined']:,} -> fills {c['fills']:,} after the edge rule "
            f"({c['dropped']} excluded; pool-only rows {c['pool_only']}); open marks {c['open']}; mature {c['mature']:,} (the doc's {RS_MATURE_NOTE:,}); "
            f"ISO weeks {c['weeks']}",
            rs_census_text(c),
            f"  rating (alone_c3, N = 3): rated {c['rated']:,} / unrated {c['unrated']} / thin pool (< {ap.POOL_FLOOR}) {c['thin']}; pool size min "
            f"{c['pool_min']} / median {c['pool_median']}; A+ {c['aplus']} (expectation {lo}-{hi}) / capped {c['capped']} / rest {c['rest']}; weeks with fewer "
            f"than 3 A+ after burn-in {ap._r(c['weeks_under_3_share'], 3)}",
            f"  ties at the cutoff: {c['ties_at_cutoff']} fills sit exactly at their cutoff member's value ({c['ties_flagged_rest']} flagged rest, "
            f"{c['ties_flagged_aplus']} A+) - disclosed in the doc: a fill whose pct is above one half scores BELOW each member tied with it"]


def not_computed_problems(cols: dict, res: dict) -> list:
    """Structural: every other feature column is empty, the engine rated ONE spec, and no percentile outside `rs_best` exists."""
    p = []
    for c in NOT_COMPUTED:
        if any(x is not None for x in cols[c]):
            p.append(f"STEP 0: the feature column {c} is not empty - another score would be computed on the sealed era")
    if set(res["score"]) != {RS_SPEC}:
        p.append(f"STEP 0: the engine rated {sorted(res['score'])}, not {RS_SPEC} alone")
    j = ap.KEY_IDX["c3"]
    other = np.delete(res["pct"], j, axis=1)
    if not np.isnan(other).all():
        p.append("STEP 0: a percentile outside rs_best was computed")
    return p


def join_problems(cols: dict, built: dict) -> list:
    """The join checks (the parent's check 3, for the one input this read has): one candidates row per fill, `rs_best` never missing, every E and D
    on the SPY calendar, (ticker, E) unique, fill_minute >= 5."""
    n = len(cols["E"])
    p = list(built["problems"])
    miss = sum(1 for x in cols[RS_COLUMN] if x is None)
    if miss:
        p.append(f"check 3: {RS_COLUMN} missing for {miss} rows")
    if any(cols["E_ci"][i] < 0 or cols["D_ci"][i] < 0 for i in range(n)):
        p.append("check 3: an E or D is not on the SPY calendar")
    keys = Counter((cols["ticker"][i], cols["E"][i]) for i in range(n))
    if any(v > 1 for v in keys.values()):
        p.append("check 3: (ticker, E) not unique")
    if any(cols["fill_minute"][i] < 5 for i in range(n)):
        p.append("check 3: a fill_minute < 5")
    return p


def rs_step0(ctx: rr.Ctx, prep: dict, say) -> tuple:
    """Build, rate, count and compare to the equality targets (no outcome column opened). Returns (cols, res, ties, census, problems)."""
    t0 = time.time()
    built = build_cols(ctx, prep)
    cols = built["cols"]
    say(f"calendar: {len(built['cal'])} SPY sessions {built['cal'][0]}..{built['cal'][-1]}; {len(cols['E']):,} rows ({sum(bool(x) for x in cols['eligible']):,} eligible) "
        f"[{time.time() - t0:.0f}s]")
    problems = join_problems(cols, built)
    res = rate_alone(cols)
    ties = ties_at_cutoff(cols, res)
    c = census(cols, prep, res, ties)
    for ln in census_text(c):
        say(ln)
    problems += ap.census_problems(c, RS_EXPECTED)
    problems += [f"STEP 0: {x}" for x in ties["problems"]]
    problems += not_computed_problems(cols, res)
    say(f"  equality targets checked: {len(RS_EXPECTED)} ({', '.join(sorted(RS_EXPECTED))}); no other score is computed: the {len(NOT_COMPUTED)} other feature "
        f"columns are empty and the engine rated {RS_SPEC} alone [{time.time() - t0:.0f}s]")
    return cols, res, ties, c, problems


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the checks (spec 4-9): features and the flag, never an outcome number
# ═════════════════════════════════════════════════════════════════════════════════════════════
def _same(a, b) -> bool:
    a, b = float(a), float(b)
    return (a != a and b != b) or a == b


def _row_same(res_a: dict, i: int, res_b: dict, j: int) -> bool:
    return (_same(res_a["score"][RS_SPEC][i], res_b["score"][RS_SPEC][j]) and _same(res_a["cutoff"][(RS_SPEC, RS_N)][i], res_b["cutoff"][(RS_SPEC, RS_N)][j])
            and res_a["flag"][(RS_SPEC, RS_N)][i] == res_b["flag"][(RS_SPEC, RS_N)][j])


def check4b_columns(ctx: rr.Ctx, prep: dict, cols: dict, res: dict) -> tuple:
    """Spec check 4, the parent's check 1 (b): every E-day-or-later candidates column (open_E .. breakout_vol_x, and base_id) permuted at the SOURCE -
    in the candidates frame, before any feature is built - and `rs_best` re-joined, the engine re-run: every score, cutoff and flag identical. The
    outcome columns are never loaded (the fills frame is read by FILL_COLS): asserted on the frame - an absent column cannot be read."""
    cands = read_rs_cands(prep["paths"]["cands"], prep["label_of"], extra=tuple(ap.SHUFFLE_COLS))
    rng = np.random.default_rng([ap.SAMPLE_SEED, zlib.crc32(b"rs_alone_check4b")])
    perm = rng.permutation(len(cands))
    for k in ap.SHUFFLE_COLS:
        cands[k] = cands[k].to_numpy()[perm]
    built = build_cols(ctx, dict(prep, cands=cands))
    res2 = rate_alone(built["cols"])
    p = []
    diff = ap._res_diff(res, res2)
    if diff:
        p.append(f"check 4 (b): {diff} with the E-day columns permuted in the candidates frame and rs_best re-joined")
    oc_in = sorted((set(prep["fills"].columns) | set(ap.FILL_COLS)) & set(ap.OUTCOME_COLS))
    if oc_in:
        p.append(f"check 4 (b): the fills frame / FILL_COLS carry the outcome columns {oc_in} - a feature could read an outcome")
    cand_in = sorted(set(prep["cands"].columns) - set(RS_CAND_COLS))
    if cand_in:
        p.append(f"check 4 (b): the run's candidates frame carries {cand_in} beyond {RS_CAND_COLS}")
    return p, [f"check 4 (b): {ap.SHUFFLE_COLS} permuted in the candidates frame ({len(cands):,} rows) before rs_best was joined, the engine re-run - every "
               f"score, cutoff and flag identical; the fills frame carries no outcome column and the candidates frame no column beyond {RS_CAND_COLS}"]


def perturb_after_d(cols: dict, D: str, rng) -> dict:
    """A copy of `cols` in which every row dated AFTER `D` (its watch night D' > D, i.e. its breakout day is later) has `rs_best`, `fill_minute` and the
    ticker randomised. Dates, weeks and the calendar index are facts of the calendar and stay."""
    out = {k: v for k, v in cols.items()}
    later = [j for j in range(len(cols["D"])) if cols["D"][j] > D]
    for k in ("rs_best", "fill_minute", "ticker"):
        out[k] = list(cols[k])
    for j in later:
        out["rs_best"][j] = round(float(rng.uniform(0.0, 100.0)), 1)
        out["fill_minute"][j] = int(rng.integers(5, 390))
        out["ticker"][j] = f"Z{int(rng.integers(0, 10**9))}"
    return out


def check4c_after_d(cols: dict, res: dict) -> tuple:
    """Spec check 4, the parent's check 1 (c): per sampled fill (50 + every A+), with every row after that fill's D randomised, the fill's score,
    cutoff and flag are identical. For this score the only inputs are the fills / candidates rows (the export contributes the date axis alone), so the
    perturbed rows ARE the rows after D: a pool that reaches past E, a cap that counts a later fill, a join on the wrong night would all move."""
    el = np.flatnonzero(np.asarray(cols["eligible"], dtype=bool))
    ap_idx = np.flatnonzero(flags(res) == ap.FLAG_APLUS)
    sample = np.unique(np.concatenate((ap.sample_rows(el, CHECK4C_SAMPLE, "rs_alone_check4c"), ap_idx)))
    rng = np.random.default_rng([ap.SAMPLE_SEED, zlib.crc32(b"rs_alone_check4c_rows")])
    bad = 0
    for i in sample:
        pert = perturb_after_d(cols, cols["D"][i], rng)
        r = rate_alone(pert)                                                 # the engine returns its arrays in INPUT order: row i is row i
        if not _row_same(res, i, r, i):
            bad += 1
    p = [f"check 4 (c): {bad} of {len(sample)} fills changed score, cutoff or flag when every row after their D was randomised"] if bad else []
    return p, [f"check 4 (c): {len(sample)} fills ({CHECK4C_SAMPLE} sampled + {len(ap_idx)} A+) - score, cutoff and flag identical with rs_best / fill_minute / "
               f"ticker randomised on every row dated after the fill's D"]


def check5_later_fills(cols: dict, res: dict) -> tuple:
    """Spec check 5, the parent's check 2: for EVERY A+ fill, remove every fill after it in (E, fill_minute, ticker) order - its score, cutoff and
    flag are unchanged."""
    ap_idx = np.flatnonzero(flags(res) == ap.FLAG_APLUS)
    n = len(cols["E"])
    order = np.lexsort((np.asarray(cols["ticker"], dtype=str), np.asarray(cols["fill_minute"], dtype=np.int64), np.asarray(cols["E_ci"], dtype=np.int64)))
    pos = np.empty(n, dtype=np.int64)
    pos[order] = np.arange(n)
    bad = 0
    for i in ap_idx:
        keep = np.flatnonzero(pos <= pos[i])                                 # every fill at or before it in fill order
        j = int(np.flatnonzero(keep == i)[0])
        r = rate_alone({k: [v[q] for q in keep] for k, v in cols.items()})
        if not _row_same(res, i, r, j):
            bad += 1
    p = [f"check 5: {bad} of {len(ap_idx)} A+ fills changed when the later fills were removed"] if bad else []
    return p, [f"check 5 (later-fill removal): all {len(ap_idx)} A+ fills - score, cutoff and flag unchanged with every later fill removed"]


def check6_counts_pool_shuffle(cols: dict, res: dict) -> tuple:
    """Spec check 6, the parent's checks 4, 6, 7: (4) A+ unique by (ticker, E), per ISO week A+ = min(3, fills at or above the cutoff), never more than 3;
    (6) the pool count of every fill equals an independent count, >= 30 for every rated fill, every week = the ISO week of its E; (7) the A+ set is
    unchanged when the input rows are shuffled (seed 702)."""
    p = []
    el = np.asarray(cols["eligible"], dtype=bool)
    weeks = np.asarray(cols["week"], dtype=object)
    fl = flags(res)
    ap_ = (fl == ap.FLAG_APLUS) & el
    keys = [(cols["ticker"][i], cols["E"][i]) for i in np.flatnonzero(ap_)]
    if len(keys) != len(set(keys)):
        p.append(f"check 6 (counts): A+ not unique by (ticker, E)")
    above = ((fl == ap.FLAG_APLUS) | (fl == ap.FLAG_CAPPED)) & el
    n_weeks = 0
    for w in set(weeks[above]):
        n_ap, n_above = int((ap_ & (weeks == w)).sum()), int((above & (weeks == w)).sum())
        n_weeks += 1
        if n_ap != min(RS_N, n_above) or n_ap > RS_N:
            p.append(f"check 6 (counts): week {w} has {n_ap} A+ for {n_above} fills at or above the cutoff (N = {RS_N})")
    pc = ap.pool_counts(cols, keys=())
    if not np.array_equal(pc["pool_n"], res["pool_n"]):
        p.append("check 6 (pool): the pool count differs from an independent count")
    rated = (fl != ap.FLAG_UNRATED) & (fl != ap.FLAG_POOL)
    thin = int((res["pool_n"][rated] < ap.POOL_FLOOR).sum())
    if thin:
        p.append(f"check 6 (pool): {thin} rated fills have a pool under {ap.POOL_FLOOR}")
    wk_bad = sum(1 for i in range(len(cols["E"])) if cols["week"][i] != ap.iso_week(cols["E"][i]))
    if wk_bad:
        p.append(f"check 6 (pool): {wk_bad} rows carry a week that is not the ISO week of their E")
    n = len(cols["E"])
    rng = np.random.default_rng([ap.SAMPLE_SEED, zlib.crc32(b"rs_alone_check6")])
    perm = rng.permutation(n)
    cols2 = {k: [np.asarray(v, dtype=object)[j] for j in perm] for k, v in cols.items()}
    res2 = rate_alone(cols2)
    if ap.aplus_set(cols, res, RS_SPEC, RS_N) != ap.aplus_set(cols2, res2, RS_SPEC, RS_N):
        p.append("check 6 (shuffle): the A+ set differs after a seed-702 shuffle of the input rows")
    return p, [f"check 6 (counts, pool, shuffle): {n_weeks} weeks asserted (A+ unique by (ticker, E); per week A+ = min(3, fills at or above the cutoff)); "
               f"pool counts equal an independent count; every rated fill's pool >= {ap.POOL_FLOOR}; the A+ set unchanged under a seed-702 shuffle"]


def tie_rule_problems(cols: dict, res: dict, ties: dict) -> list:
    """The doc's disclosed property, on the real inputs: a fill tied with the cutoff member whose own pct is above one half is NEVER A+ (it scores below
    each member tied with it, p < p + (p - 1/2)/(n - 1))."""
    el = np.asarray(cols["eligible"], dtype=bool)
    fl = flags(res)
    pct = res["pct"][:, ap.KEY_IDX["c3"]]
    bad = [i for i in np.flatnonzero(ties["tie"] & el) if pct[i] > 0.5 and fl[i] == ap.FLAG_APLUS]
    return [f"check 9 (tie rule): {len(bad)} fills tied with their cutoff member at pct > 1/2 are A+"] if bad else []


def run_checks(ctx: rr.Ctx, prep: dict, cols: dict, res: dict, ties: dict, say) -> tuple:
    """Spec checks 4 (b)(c), 5, 6 and 9 on the inputs - features and the flag, never an outcome number."""
    problems, lines = [], []
    steps = [lambda: check4b_columns(ctx, prep, cols, res), lambda: check4c_after_d(cols, res), lambda: check5_later_fills(cols, res),
             lambda: check6_counts_pool_shuffle(cols, res)]
    for fn in steps:
        t0 = time.time()
        p, ln = fn()
        problems += p
        lines += ln
        for x in ln:
            say(f"  {x} [{time.time() - t0:.0f}s]")
    tp = tie_rule_problems(cols, res, ties)
    from scripts.probes._cb_backtest import rs_alone_fixtures
    gp = rs_alone_fixtures.run_golden()
    problems += tp + [f"check 9 (golden fixtures): {x}" for x in gp]
    g = (f"check 9 (golden tie fixtures T1 / T2 / T3 on the committed code): {'pass' if not gp else 'FAIL: ' + '; '.join(gp)}; the tie rule on the real "
         f"inputs: {'no fill tied with its cutoff member at pct > 1/2 is A+' if not tp else tp[0]}")
    lines.append(g)
    say("  " + g)
    return problems, lines


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the bar, the paired veto, the consequence line, the expectations
# ═════════════════════════════════════════════════════════════════════════════════════════════
def c0_published() -> dict:
    return ap.C0_PUBLISHED["holdout"]


def alone_verdict(g: dict, c0: dict) -> tuple:
    """The parent's PASS bar with the 2025-26 numbers (spec §Bar): the integer outlier test count_ge10 x 7,531 >= 2 x 89 x n, C0 = the published
    7,531 mature fills (mean R -0.129, >= 5R 2.95 per 100, >= 10R 89)."""
    pub = c0_published()
    return ap.verdict_of(g, c0, pub["n"], pub["ge10"])


def outlier_test(g: dict) -> dict:
    pub = c0_published()
    n, cnt = int(g.get("n") or 0), int(g.get("count_ge10") or 0)
    lhs, rhs = cnt * pub["n"], 2 * pub["ge10"] * n
    return {"count_ge10": cnt, "n": n, "lhs": lhs, "rhs": rhs, "met": lhs >= rhs, "formula": f"count_ge10 x {pub['n']} >= 2 x {pub['ge10']} x n"}


def rs_consequence(verdict: str, paired_reading: str) -> dict:
    """The spec's three-cell table: PASS (and the paired bar not 'picks worse') -> RECORD; CAN'T TELL -> not recorded, the rating line ends; FAIL ->
    not recorded, the line ends. 'Picks worse' is a veto whatever the verdict."""
    cls = ap._verdict_class(verdict)
    if paired_reading == "picks worse":
        return {"cell": "NOT RECORDED", "record": False, "text": f"{cls}, but the paired A+ minus REST bar reads 'picks worse' - a veto whatever the verdict: NOT RECORDED. "
                f"The rating line on these seven ingredients ENDS."}
    if cls == "PASS":
        return {"cell": "RECORD", "record": True, "text": "PASS: RECORD - the forward shadow stores the rs_best-alone score, cutoff, pool size and flag beside its rows. "
                "This is a recorder change: no order path, no money. Paper is a proposal to him; live is his sign-off (THE LINE)."}
    if cls == "FAIL":
        return {"cell": "NOT RECORDED", "record": False, "text": "FAIL: NOT RECORDED - the rating line on these seven ingredients ENDS (the rating does not select on these ingredients)."}
    return {"cell": "NOT RECORDED", "record": False, "text": "CAN'T TELL: NOT RECORDED - the rating line on these seven ingredients ENDS (the rating does not select on these ingredients). "
            "It is reported to him with the alone table of all three eras' readable rows."}


def expectations(group: dict, c0: dict, counts: dict) -> list:
    """The registered expectations (a miss is reported first and changes NO rule): A+ n 215-279; C0 under pp reads as published."""
    lo, hi = ap.EXPECT_APLUS_N["holdout"]
    pub = c0_published()
    out = [f"A+ n (N = 3) {counts['aplus']} in {lo}-{hi}: {'met' if lo <= counts['aplus'] <= hi else 'MISS'}"]
    c0_ok = (c0["mean_r"] is not None and abs(c0["mean_r"] - pub["mean_r"]) <= 0.0005 and abs(c0["ge5_per100"] - pub["ge5_per100"]) <= 0.005
             and c0["integers_match"])
    out.append(f"C0 under pp reads as published (mean R {ap._r(c0['mean_r'], 4)} vs {pub['mean_r']:+.3f}; >= 5R {ap._r(c0['ge5_per100'], 3)} vs {pub['ge5_per100']} "
               f"per 100; >= 10R {c0['count_ge10']} of {c0['n']:,} vs {pub['ge10']} of {pub['n']:,}): {'met' if c0_ok else 'MISS'}")
    return out


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the outcomes, the report rows, the table
# ═════════════════════════════════════════════════════════════════════════════════════════════
def report_rows(cols: dict, res: dict, oc: dict, boot, c0: dict) -> tuple:
    """The one reported row (alone_c3, N = 3) with its statistics and verdict, and the paired bar (A+ minus REST: the rated fills not in A+, capped
    ones included, mature)."""
    el = np.asarray(cols["eligible"], dtype=bool)
    fl = flags(res)
    pub = c0_published()
    g = ap.group_of(cols, oc, fl == ap.FLAG_APLUS, ap.boot_key("holdout", RS_N, RS_SPEC), boot)
    g.update(spec=RS_SPEC, N=RS_N, period="holdout", unrated=int(((fl == ap.FLAG_UNRATED) & el).sum()), capped=int(((fl == ap.FLAG_CAPPED) & el).sum()),
             rest=int(((fl == ap.FLAG_REST) & el).sum()))
    g["verdict"], g["why"] = alone_verdict(g, c0) if g["n"] else ("CAN'T TELL", "n = 0")
    g["median_width_vs_c0"] = (g["median_width_adr"] - c0["median_width_adr"]) if g.get("median_width_adr") is not None else None
    mature = (oc["mature"] == 1) & el
    a = np.flatnonzero((fl == ap.FLAG_APLUS) & mature)
    b = np.flatnonzero(((fl == ap.FLAG_REST) | (fl == ap.FLAG_CAPPED)) & mature)
    months = np.asarray(cols["fill_month"], dtype=object)
    paired = ap.paired_delta(oc["realized_r"][a], months[a], oc["realized_r"][b], months[b], ap.pair_key("holdout", RS_N, RS_SPEC))
    fm = np.asarray(cols["fill_minute"], dtype=np.int64)
    wd = np.asarray(cols["weekday"], dtype=np.int64)
    ap_m = (fl == ap.FLAG_APLUS) & el
    mix = {"aplus_fm_bins": ap.bins_of(fm[ap_m]), "c0_fm_bins": ap.bins_of(fm[el]), "aplus_weekday": tuple(int((wd[ap_m] == k).sum()) for k in range(5)),
           "c0_weekday": tuple(int((wd[el] == k).sum()) for k in range(5))}
    return g, paired, mix


TABLE_BASE = ["ticker", "D", "E", "K", "period", "eligible", "week", "weekday", "fill", "fill_minute", "fill_month", "adr20", "width_adr", "stop", "mature",
              "open_mark", "early_close", "pool_n", RS_COLUMN]


def table_cols() -> list:
    return TABLE_BASE + ["pct_c3", f"score_{RS_SPEC}", f"cutoff_{RS_SPEC}_n{RS_N}", f"flag_{RS_SPEC}_n{RS_N}", "cutoff_member_value", "tie_at_cutoff",
                         "status", "realized_r", "pnl_adr"]


def table_rows(cols: dict, res: dict, ties: dict, oc: dict) -> list:
    out = []
    j = ap.KEY_IDX["c3"]
    for i in range(len(cols["E"])):
        r = {k: cols[k][i] for k in TABLE_BASE if k in cols}
        r["period"], r["pool_n"] = "holdout", int(res["pool_n"][i])
        r["eligible"] = int(bool(cols["eligible"][i]))
        r["pct_c3"] = res["pct"][i, j]
        r[f"score_{RS_SPEC}"] = res["score"][RS_SPEC][i]
        r[f"cutoff_{RS_SPEC}_n{RS_N}"], r[f"flag_{RS_SPEC}_n{RS_N}"] = res["cutoff"][(RS_SPEC, RS_N)][i], res["flag"][(RS_SPEC, RS_N)][i]
        r["cutoff_member_value"], r["tie_at_cutoff"] = ties["v_cut"][i], int(bool(ties["tie"][i]))
        r["status"], r["realized_r"], r["pnl_adr"] = oc["status"][i], oc["realized_r"][i], oc["pnl_adr"][i]
        out.append(r)
    return out


def report_text(group: dict, paired: dict, mix: dict, c0: dict, c, exp_lines: list, check_lines: list, notes: list, consequence: dict, outlier: dict, rt) -> str:
    pub = c0_published()
    L = ["#705 RS-LEADERSHIP-ALONE READ - period holdout (the sealed 2025-26) - tl - ORH5 - pp - mature walks (alone_c3 at N = 3; the only score computed)"]
    L += notes
    L.append("")
    L.append(f"C0 (the table's own, every mature pp / orh5 / tl row): n {c0['n']:,}, mean R {ap._r(c0['mean_r'], 4)}, >= 5R {ap._r(c0['ge5_per100'], 3)} / 100, "
             f">= 10R {c0['count_ge10']} ({ap._r(c0['ge10_per100'], 3)} / 100); published {pub}; median stop width {ap._r(c0['median_width_adr'], 3)} ADR")
    g = group
    row = [f"{RS_SPEC} N={RS_N}", g["n_filled"], g["n"], ap._r(g.get("mean_r"), 3), f"[{ap._r(g.get('ci_lo'), 2)}, {ap._r(g.get('ci_hi'), 2)}]" if g.get("n", 0) >= 2 else "",
           ap._r(g.get("win_rate"), 3), ap._r(g.get("ge5_per100"), 2), ap._r(g.get("ge10_per100"), 2), ap._r(g.get("ge20_per100"), 2), ap._r(g.get("sum_r"), 1),
           ap._r(g.get("mean_pnl_adr"), 3), ap._r(g.get("median_width_adr"), 3), f"{g.get('count_ge10', '')}: {g.get('tail_tickers', '')}t/{g.get('tail_months', '')}m" if g.get("n") else "",
           g["unrated"], g["capped"], g["verdict"], g["why"]]
    L.append(rt.table([row], ["row", "filled", "n", "mean R", "95% CI", "win", ">=5R/100", ">=10R/100", ">=20R/100", "total R", "ADR P&L", "med width", ">=10R spread",
                              "unrated", "capped", "verdict", "why"]))
    L.append("")
    L.append(f"OUTLIER BAR (integers): {outlier['formula']}: {outlier['count_ge10']} x {pub['n']} = {outlier['lhs']} vs 2 x {pub['ge10']} x {outlier['n']} = "
             f"{outlier['rhs']} -> {'met' if outlier['met'] else 'NOT met'}")
    L.append(f"PAIRED (A+ minus REST, N = 3, mature): n {paired['n_a']} vs {paired['n_b']}, mean delta {ap._r(paired.get('mean'), 4)} [{ap._r(paired.get('lo'), 3)}, "
             f"{ap._r(paired.get('hi'), 3)}] over {paired['months']} months ({paired['discarded']} empty draws redrawn) -> {paired['reading']}")
    L.append(f"A+ fill-minute mix {mix['aplus_fm_bins']} vs C0 {mix['c0_fm_bins']}; weekday mix (Mon..Fri) {mix['aplus_weekday']} vs C0 {mix['c0_weekday']} - reported, never a finding")
    L.append(f"ties at the cutoff: {c['ties_at_cutoff']} fills ({c['ties_flagged_rest']} rest, {c['ties_flagged_aplus']} A+); rated {c['rated']:,}, A+ {c['aplus']}, capped {c['capped']}, rest {c['rest']}")
    L.append("")
    L.append(f"CONSEQUENCE: {consequence['text']}")
    L.append("")
    L.append("EXPECTATIONS (a miss is reported first and changes NO rule):")
    L += [f"  {x}" for x in exp_lines]
    L.append("")
    L.append("CHECKS:")
    L += [f"  {x}" for x in check_lines]
    return "\n".join(L)


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the independent re-derivation (spec check 8): MATCH before the verdict is written
# ═════════════════════════════════════════════════════════════════════════════════════════════
def set_match_problems(cols: dict, res: dict, rd: dict, tol: float = 1e-12) -> list:
    """The feature-only half of the MATCH: the identical (ticker, E) A+ set first, then every eligible row's score and cutoff (the re-derivation's
    pandas ranks reproduce the engine's mid-rank arithmetic exactly)."""
    ours, theirs = ap.aplus_set(cols, res, RS_SPEC, RS_N), rd["aplus"]
    if ours != theirs:
        return [f"the A+ set differs on ({RS_SPEC}, N = {RS_N}): {len(ours - theirs)} only ours, {len(theirs - ours)} only re-derived"]
    p = []
    sc, cu = res["score"][RS_SPEC], res["cutoff"][(RS_SPEC, RS_N)]
    bad_s = bad_c = 0
    for i in np.flatnonzero(np.asarray(cols["eligible"], dtype=bool)):
        key = (cols["ticker"][i], cols["E"][i])
        a, b = sc[i], rd["score"].get(key, float("nan"))
        bad_s += not ((a != a and b != b) or abs(a - b) <= tol)
        a, b = cu[i], rd["cutoff"].get(key, float("nan"))
        bad_c += not ((a != a and b != b) or abs(a - b) <= tol)
    if bad_s:
        p.append(f"{bad_s} eligible fills' scores differ from the re-derivation")
    if bad_c:
        p.append(f"{bad_c} eligible fills' cutoffs differ from the re-derivation")
    return p


def match_problems(cols: dict, res: dict, group: dict, paired: dict, rd: dict, tol: float = 1e-9) -> list:
    """First the identical A+ set (and scores / cutoffs); only then n / mean R / the interval / the paired delta / every PASS component (the
    >= 10R integer test included) and the verdict class. A numeric mismatch names the component and the gap size - never the values."""
    p = set_match_problems(cols, res, rd)
    if p:
        return p

    def gap(a, b) -> str:
        if a is None or b is None or a != a or b != b:
            return "one side missing / NaN"
        return f"|difference| {abs(float(a) - float(b)):.3g}"
    core = rd["core"]
    for k in ("n", "mean_r", "ci_lo", "ci_hi", "ge5_per100", "mean_pnl_adr", "count_ge10", "tail_tickers", "tail_months"):
        a, b = group.get(k), core.get(k)
        if a is None or b is None or (isinstance(a, float) and abs(a - b) > tol) or (not isinstance(a, float) and a != b):
            p.append(f"alone_c3 N = 3 {k} differs from the re-derivation ({gap(a, b)})")
    if group["verdict"] != core.get("verdict"):
        p.append("the verdict class differs from the re-derivation")
    pub = c0_published()
    ours_outlier = group["count_ge10"] * pub["n"] >= 2 * pub["ge10"] * group["n"]
    theirs_outlier = core["count_ge10"] * pub["n"] >= 2 * pub["ge10"] * core["n"]
    if ours_outlier != theirs_outlier:
        p.append("the integer outlier test differs from the re-derivation")
    th = rd["paired"]
    for k in ("mean", "lo", "hi"):
        a, b = paired.get(k), th.get(k)
        if not ((a != a and b != b) or (a is not None and b is not None and abs(a - b) <= tol)):
            p.append(f"paired {k} differs from the re-derivation ({gap(a, b)})")
    if paired["reading"] != th["reading"]:
        p.append("the paired reading differs from the re-derivation")
    return p


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the read: STEP 0 -> checks -> outcomes -> bars -> the re-derivation -> the verdict
# ═════════════════════════════════════════════════════════════════════════════════════════════
def rs_outputs(ctx: rr.Ctx) -> tuple:
    return (f"trades_{ctx.period}_{RS_TAG}.tsv.gz", f"{RS_TAG}_report_{ctx.period}.tsv", f"{RS_TAG}_report_{ctx.period}.txt")


def rs_frozen(ctx: rr.Ctx) -> dict:
    """The registration's pin list (the doc's footer): the engine module the stage imports, the re-derivation module, the golden fixtures module, the
    two exitpb tables, the two P5 tables, `candidates.tsv`, `watch.tsv.gz` and the daily export (the driver adds the runner, the scaffold and this
    spec module). The P5 and watch tables are pinned as the doc lists them though this score opens neither."""
    d = ctx.dirs["cb702"]
    here = Path(__file__).resolve().parent
    files = {"aplus module": here / "aplus_read.py", "rederivation module": here / "aplus_rederive.py",
             "golden fixtures module": here / "rs_alone_fixtures.py"}
    for name in ("trades_discovery_exitpb.tsv.gz", "trades_holdout_exitpb.tsv.gz", "trades_discovery_p5.tsv.gz", "trades_holdout_p5.tsv.gz", "candidates.tsv",
                 "watch.tsv.gz"):
        files[f"cb702/out/{name}"] = d / "out" / name
    files["cb702/daily_closes_all.csv.gz"] = d / "daily_closes_all.csv.gz"
    return files


def rs_dry_run(ctx: rr.Ctx, prep: dict, existing: list) -> str:
    """`--dry-run`: STEP 0 against its equality targets (no outcome column opened, nothing written). `--dry-run --self-check` adds the checks 4 (b)(c), 5,
    6, 9 and the re-derivation's A+ SET / scores / cutoffs (still no outcome)."""
    say = ctx.say
    pre = prep["precondition"]
    say(f"RS-ALONE DRY RUN (freeze check {ctx.freeze}; features only): period holdout: {len(prep['rows']):,} eligible rows from {prep['paths']['fills']}; outputs "
        f"already on disk: {[q.name for q in existing] or 'none'}")
    say(f"  precondition: the A+ rating read 2017-21 {pre['pre']} (paired {pre['pre_paired']}) x 2022-24 {pre['discovery']} (paired {pre['discovery_paired']}) -> "
        f"{pre['cell']}; next registration {pre['next_registration']}")
    cols, res, ties, c, problems = rs_step0(ctx, prep, say)
    if getattr(ctx.args, "self_check", False):
        p2, _lines = run_checks(ctx, prep, cols, res, ties, say)
        problems += p2
        from scripts.probes._cb_backtest import aplus_rederive
        t0 = time.time()
        rd = aplus_rederive.rederive_alone_c3(prep["paths"], "holdout", ap.C0_PUBLISHED["holdout"], outcomes=False, log=say)
        mp = set_match_problems(cols, res, rd)
        say(f"  check 8 (re-derivation, features only) [{time.time() - t0:.0f}s]: {'the A+ set, every score and every cutoff MATCH (pandas, no runner code)' if not mp else 'MISMATCH: ' + '; '.join(mp)}")
        problems += [f"check 8: {x}" for x in mp]
    return ("STEP 0 PASSED: every equality target met" + ("; SELF-CHECK PASSED" if getattr(ctx.args, "self_check", False) else "")) if not problems else \
        "STEP 0 / SELF-CHECK FAILED (the read would exit 3):\n" + "\n".join("  - " + x for x in problems)


def rs_body(ctx: rr.Ctx, prep: dict, say) -> "rr.Verdict | int":
    rt = ctx.rt
    cols, res, ties, c, problems = rs_step0(ctx, prep, say)
    if problems:
        say("STEP 0 FAILED: " + "; ".join(problems) + " - the read stops here; no outcome column was opened")
        return 3
    problems, check_lines = run_checks(ctx, prep, cols, res, ties, say)
    if problems:
        say("IMPLEMENTATION CHECK FAILED (" + str(len(problems)) + "): " + "; ".join(problems) + " - the report is NOT written; no outcome column was opened")
        return 3
    # the outcomes - opened ONLY now
    paths = prep["paths"]
    outcomes = ap.read_outcomes(paths["fills"])
    outcomes.update(ap.read_outcomes(paths["pool_fills"]))
    oc, p = ap.join_outcomes(cols, outcomes)
    if p:
        say("OUTCOME JOIN FAILED: " + "; ".join(p[:5]))
        return 3
    el = np.asarray(cols["eligible"], dtype=bool)
    c0 = ap.c0_baseline(cols, oc, ap.read_outcomes(paths["fills"]), "holdout")
    c0["median_width_adr"] = float(np.median(np.asarray(cols["width_adr"], dtype=float)[el & (oc["mature"] == 1)]))
    if not c0["integers_match"]:
        say(f"C0 INTEGERS DIFFER: the table's mature n {c0['n']} / >= 10R count {c0['count_ge10']} are not the registered {c0_published()['n']} / "
            f"{c0_published()['ge10']} - the outlier bar's constants do not describe this table; the report is NOT written")
        return 3
    group, paired, mix = report_rows(cols, res, oc, rt.block_bootstrap_ci, c0)
    # check 7 (outcomes read, never re-walked): every A+ row's realized_r equals the pinned exitpb row, re-read
    pinned = ap.read_outcomes(paths["fills"])
    ap_idx = np.flatnonzero(flags(res) == ap.FLAG_APLUS)
    bad = sum(1 for i in ap_idx if abs(pinned[(cols["ticker"][i], cols["D"][i], cols["E"][i], cols["K"][i])][1] - oc["realized_r"][i]) > 1e-9)
    if bad:
        say(f"CHECK 7 (outcomes) FAILED: {bad} A+ rows differ from the pinned exitpb rows")
        return 3
    check_lines.append("check 7 (outcomes): every A+ row's realized_r equals the pinned exitpb row (1e-9) - read, never re-walked")
    # check 8: the independent re-derivation - VERDICT MATCH before the result is written
    from scripts.probes._cb_backtest import aplus_rederive
    t0 = time.time()
    rd = aplus_rederive.rederive_alone_c3(paths, "holdout", ap.C0_PUBLISHED["holdout"], outcomes=True, log=say)
    mp = match_problems(cols, res, group, paired, rd)
    say(f"RE-DERIVATION (pandas, no runner code) [{time.time() - t0:.0f}s]: {'VERDICT MATCH' if not mp else 'MISMATCH: ' + '; '.join(mp)}")
    if mp:
        say("the result is NOT written")
        return 3
    check_lines.append("check 8 (re-derivation): VERDICT MATCH - the alone_c3 A+ set, every eligible score and cutoff, n, mean R, both intervals (the PASS interval "
                       "and the paired), every PASS component (the >= 5R share, ADR P&L, the >= 10R integer comparison and its spread) and the verdict class")
    outlier = outlier_test(group)
    consequence = rs_consequence(group["verdict"], paired["reading"])
    exp_lines = expectations(group, c0, c)
    notes = [f"DATA CHECKS: freeze {ctx.freeze}; precondition met ({prep['precondition']['cell']}, next registration {prep['precondition']['next_registration']}); STEP 0 equal to "
             f"the registered counts; implementation checks passed; re-derivation VERDICT MATCH"]
    text = report_text(group, paired, mix, c0, c, exp_lines, check_lines, notes, consequence, outlier, rt)
    table_name, rep_tsv, rep_txt = rs_outputs(ctx)
    trows = table_rows(cols, res, ties, oc)
    tcols = table_cols()
    with ctx.partial_write(table_name) as fh:
        fh.write(rt.rows_to_gz([tcols]))
        fh.write(rt.rows_to_gz([[r.get(k) for k in tcols] for r in trows]))
    rt.write_tsv(ctx.out / rep_tsv, [group], ap.REPORT_COLS)
    rt.write_tsv(ctx.small / rep_tsv, [{k: (round(v, 6) if isinstance(v, float) else v) for k, v in group.items()}], ap.REPORT_COLS)
    (ctx.out / rep_txt).write_text(text + "\n")
    (ctx.small / rep_txt).write_text(text + "\n")
    print(text)
    say(f"WROTE {ctx.out / table_name} ({len(trows):,} rows), {ctx.out / rep_tsv}, {ctx.small / rep_txt}")
    data = {"period": "holdout", "spec": RS_SPEC, "N": RS_N, "verdict": group["verdict"], "why": group["why"], "n": group["n"], "aplus_n": c["aplus"],
            "components": {k: group.get(k) for k in ("mean_r", "ci_lo", "ci_hi", "mean_pnl_adr", "ge5_per100", "count_ge10", "ge10_per100", "tail_tickers", "tail_months",
                                                      "median_width_adr")},
            "outlier_test": outlier, "c0": {k: c0.get(k) for k in ("n", "mean_r", "ge5_per100", "count_ge10", "ge10_per100", "median_width_adr")},
            "paired": {k: paired.get(k) for k in ("n_a", "n_b", "mean", "lo", "hi", "reading", "discarded", "key")}, "consequence": consequence,
            "precondition": prep["precondition"], "step0": {k: c[k] for k in ("joined", "fills", "open", "weeks", "dropped", "mature", "rated", "unrated", "thin",
                                                                             "aplus", "capped", "rest", "ties_at_cutoff", "ties_flagged_rest", "ties_flagged_aplus")},
            "expectations": exp_lines, "rederivation": "MATCH", "written": time.strftime("%Y-%m-%d")}
    lines = (f"#705 RS-LEADERSHIP-ALONE VERDICT FILE - period holdout - written {time.strftime('%Y-%m-%d')}",
             f"alone_c3 N = 3: {group['verdict']} ({group['why']}); n {group['n']}, mean R {ap._r(group.get('mean_r'), 4)} [{ap._r(group.get('ci_lo'), 3)}, {ap._r(group.get('ci_hi'), 3)}], "
             f">= 5R {ap._r(group.get('ge5_per100'), 3)} / 100, >= 10R {group.get('count_ge10')} ({group.get('tail_tickers')}t / {group.get('tail_months')}m), "
             f"ADR P&L {ap._r(group.get('mean_pnl_adr'), 4)}; outlier test {outlier['count_ge10']} x {c0_published()['n']} = {outlier['lhs']} vs {outlier['rhs']}: "
             f"{'met' if outlier['met'] else 'not met'}",
             f"paired A+ minus REST: {paired['reading']} [{ap._r(paired.get('lo'), 3)}, {ap._r(paired.get('hi'), 3)}]; re-derivation: VERDICT MATCH",
             f"consequence: {consequence['text']}")
    return rr.Verdict(data, lines)


RS_ALONE_READ = rr.RegisteredRead(name="rs-alone-read", tag=RS_TAG, doc=RS_DOC, frozen=rs_frozen, prepare=rs_prepare, outputs=rs_outputs, dry_run=rs_dry_run,
                                  body=rs_body, periods=RS_PERIODS)
REGISTERED = {RS_ALONE_READ.name: RS_ALONE_READ}
