"""Stage 1f shared code: era context (store bars, guard / flag dates), the night benchmarks B1 / B2, thirds helpers.
SEAL: era-B reads the sealed copy only (lib.setup_store asserts D.cal[-1] < 2025-01-01); guard / flag dates after 2024-12-31 are dropped at parse."""
import sys, bisect
from collections import defaultdict
sys.path.insert(0, "/Users/alvinfung/apollo_the_wise/scripts/probes/_breakout_winner_study_1124/stage1de")
sys.path.insert(0, "/Users/alvinfung/apollo_the_wise/scripts/probes/_breakout_winner_study_1124/stage1f")
from lib import *                                    # noqa  (common: assert_docs, REPO, DATA, OUT_DATA, CUT ...; setup_store, work, G, bv, cb, B, runner, R)
from agents.market_intelligence import breakout_v1_list as BL
from agents.market_intelligence import breakout_v1_pick_model as PM
import ff

STAGE = Path(__file__).resolve().parent
FLAG_KLASSES = {"known_adjustment_event", "discontinuous_across_known_adjustment"}
NONFEAT_COLS = ["has_e", "fire", "hE", "lE", "oE", "fired_live"]     # E-dependent columns of the list parquet (never features)


def parse_guard(path):
    out = {}
    for i, ln in enumerate(open(path)):
        f = ln.rstrip("\n").split("\t")
        if i == 0:
            ik, ib = f.index("symbol"), f.index("breaks"); continue
        if len(f) <= ib or not f[ib]:
            continue
        keep = [x for x in (y.split(":")[0] for y in f[ib].split(";")) if x <= CUT]
        if keep:
            out[f[ik]] = sorted(keep)
    return out


def parse_flags(path):
    out = defaultdict(list)
    for i, ln in enumerate(open(path)):
        f = ln.rstrip("\n").split("\t")
        if i == 0:
            ik, it, id_ = f.index("klass"), f.index("ticker"), f.index("date"); continue
        if f[id_] > CUT or f[ik] not in FLAG_KLASSES:
            continue
        out[f[it]].append(f[id_])
    return {k: sorted(v) for k, v in out.items()}


def load_dates():
    gA = None  # era A guard comes from the store (S.breaks), set in EraCtx
    gB = parse_guard(REPO / "scripts/backtest_data_audit/runs_2026-10-23/universe/symbol_guard_B.tsv")
    fA = parse_flags(DATA / "cb702_pre_v2/audit_1023/price/A_flags.tsv")
    fB = parse_flags(DATA / "audit_runs_2026-10-23/B_flags.tsv")
    assert max(max(v) for v in gB.values()) <= CUT and max(max(v) for v in fB.values()) <= CUT
    return gB, fA, fB


class EraCtx:
    """One era's store + bars cache + date lists. `feats(row)` computes the features of one event from the store's CURRENT arrays
    (the corrupt-E test mutates them in a forked child), optionally with an explicit (o,h,l,c,v) override."""
    def __init__(self, era, S, cal, guard, flags):
        self.era, self.S, self.cal, self.guard, self.flags = era, S, cal, guard, flags
        self.cache = {}

    def series(self, t):
        if t not in self.cache:
            D = self.S.D; k = D.tid[t]; a, b = int(D.start[k]), int(D.stop[k])
            self.cache[t] = (k, a, [D.cal[i] for i in D.ci[a:b]], D.ci[a:b], D.o[a:b], D.h[a:b], D.l[a:b], D.c[a:b], D.v[a:b])
        return self.cache[t]

    def feats(self, row, arrays=None, o_override=None):
        t = row["ticker"]; k, a, d, ci, o, h, l, c, v = self.series(t)
        if arrays is not None:
            o, h, l, c, v = arrays
        Di = int(np.searchsorted(ci, int(row["ci"])))
        assert int(ci[Di]) == int(row["ci"])
        raw_close = float(self.S.raw_factor[a + Di]) * float(self.S.D.c[a + Di])
        raw_src = int(self.S.raw_src[a + Di])
        return ff.features_for(bv=bv, cb=cb, B=B, cal=self.cal, d=d, ci=ci, o=o, h=h, l=l, c=c, v=v, Di=Di, row=row, raw_close=raw_close,
                               raw_src=raw_src, era=self.era, flag_dates=self.flags.get(t, []), guard_dates=self.guard.get(t, []), o_override=o_override)


def night_benchmarks(nr):
    """B1 (pick score) and B2 (order score) for one night. nr = DataFrame of the night's BRIDGE rows (list + context-only, as live). The pick
    model's ranks run over the list PLUS the names only a context gate removed; the order score over the list only (BL.rank_rows).
    Returns {ticker: (B1, B2)} for the listed (failed == '') names. NaN -> None before pct_rank (it skips only None)."""
    def nn(x):
        return None if (x is None or (isinstance(x, float) and not np.isfinite(x))) else float(x)
    inputs, tick = [], []
    for r in nr.itertuples(index=False):
        lv, cl, adr = nn(r.level), nn(r.close), nn(r.adr20)
        dl = bv._f((lv / cl - 1) / adr) if (lv is not None and cl and adr) else None
        inputs.append({"rs_1m": nn(r.rs_1m), "rs_3m": nn(r.rs_3m), "rs_6m": nn(r.rs_6m), "prior_move": nn(r.prior_move), "runup6m": nn(r.runup6m),
                       "depth_adr": nn(r.depth_adr), "base_len": nn(r.base_len), "spread10_adr": nn(r.spread10_adr), "adr20": adr,
                       "dollar_vol20": nn(r.dollar_vol20), "dist_52w": nn(r.dist_52w), "dist_level": dl, "vs_ema21_adr": nn(r.vs_ema21_adr),
                       "since_low": nn(r.since_low), "first_base": 1.0 if int(r.bases_before) == 0 else 0.0, "group_strength": nn(r.group_strength)})
        tick.append((r.ticker, r.failed == ""))
    scores = BL.pick_scores(inputs)
    lst = [(t, nn(r.runup6m_adr), nn(r.spread10_adr)) for t, r in zip([x[0] for x in tick], nr.itertuples(index=False)) if r.failed == ""]
    rows = [{"ticker": t, "runup6m_adr": a, "spread10_adr": b} for t, a, b in lst]
    BL.rank_rows(rows)
    order = {r["ticker"]: r["order_score"] for r in rows}
    return {t: (scores[i], order.get(t)) for i, (t, is_l) in enumerate(tick) if is_l}


# ---- thirds helpers (copied from the EP study's stats.py, prereg 5.1: np.array_split thirds, tied blocks never split, mid-rank, lower middle)
def thirds_block(vals, midrank=True):
    n = len(vals)
    order = np.argsort(vals, kind="stable")
    pos_third = np.concatenate([np.full(len(p), k) for k, p in enumerate(np.array_split(np.arange(n), 3))])
    out = np.empty(n, dtype=np.int8)
    sv = vals[order]
    a = 0
    while a < n:
        b = a
        while b + 1 < n and sv[b + 1] == sv[a]:
            b += 1
        out[order[a:b + 1]] = pos_third[(a + b) // 2]
        a = b + 1
    return out


def assign_thirds(df, col, keys, min_n=6):
    out = np.full(len(df), -1, dtype=np.int8)
    x = df[col].to_numpy(dtype=float); ok = np.isfinite(x)
    sub = df[ok]
    for _, idx in sub.groupby(keys, sort=False).indices.items():
        pos = np.flatnonzero(ok)[idx]
        if len(pos) < min_n:
            continue
        out[pos] = thirds_block(x[pos])
    return out
