#!/usr/bin/env python3
"""BLIND verifier of the Stage 0 checks (breakout rebuild, 2026-11-02). Written WITHOUT reading stage0/s0*.py.

Scorecard = Qullamaggie's 269 dated breakout buys (qm_breakouts_v1_gates.tsv.gz) and the 26 big winners among them
(membership only, as 11_starting_point.py defines it). Scores = how many of Qullamaggie's buys a rule catches and how
many names it lets through a day. NO returns are read or used anywhere else. Nothing dated 2025-01-01 or later is read:
era A = cb702_pre_v2 (ends 2022-06-30); era B = cb702's daily export STREAM-FILTERED in memory to dates < 2025 before a
price is parsed (the same filter as v1_replay.sealed_copy_of_daily, but no file is written); minute files dated 2025+
are never opened.

Independent recomputation:
  (1) list rules 1-7 from the per name-night feature table (thresholds re-derived from the table; also the spec's
      ROUNDED constants, which the Saturday build will pin);
  (2) every bar feature from the daily stores (6-month move, last-10-close spread, 10/50-session volume ratio, the
      5-day-high level, the next stored session) for era A AND era B;
  (3) the order score, the per-night top-N, the per-day firing top-5/top-10;
  (4) the intraday buy: MY OWN tick loop around the LIVE pure functions (breakout_v1_entry.evaluate / _terminal_reason /
      stop_at_fill_decision / order_manager.stop_limit_buy_price / CHASE_RISK_INFLATION_CAP), with the live re-price
      path (_replace -> width_at_expected_fill -> submit_entry #500 + chase cap) modelled; then a per-buy diff against
      v1_replay.simulate_entry (the builder's stated engine).
Writes only inside this folder (verify.txt + _cache_*.parquet + verify_check1_buys.tsv)."""
import gzip, io, json, os, random, sys, time
from collections import Counter
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

REPO = "/Users/alvinfung/apollo_the_wise"
sys.path.insert(0, REPO)
HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)
FEAT = "/Users/alvinfung/apollo_data/qm_breakouts_1102"
DATA = "/Users/alvinfung/apollo_data"
PRE = f"{DATA}/cb702_pre_v2"
CBD = f"{DATA}/cb702"
SEAL = "2025-01-01"
ERA_A_D_LAST = "2022-03-31"

from scripts.probes._cb_backtest import runner  # noqa: E402
from agents.market_intelligence.broker import breakout_v1_entry as bve  # noqa: E402
from agents.market_intelligence.broker.order_manager import stop_limit_buy_price, CHASE_RISK_INFLATION_CAP  # noqa: E402
from agents.market_intelligence import breakout_v1 as bv  # noqa: E402

LOG = []


def say(s=""):
    print(s, flush=True)
    LOG.append(str(s))


def flush_log():
    open(f"{HERE}/verify.txt", "w").write("\n".join(LOG) + "\n")


def clock(m):
    if m is None or (isinstance(m, float) and np.isnan(m)):
        return "-"
    m = int(m)
    return f"{9 + (30 + m) // 60:02d}:{(30 + m) % 60:02d}"


# ═════════════════════════════════════════════════════════════════════════════════════════════════
# 0. Qullamaggie's buys + the big-winner MEMBERSHIP (no R used beyond the >= 5 label, as 11_starting_point.py)
# ═════════════════════════════════════════════════════════════════════════════════════════════════
Q = pd.read_csv(f"{PARENT}/qm_breakouts_v1_gates.tsv.gz", sep="\t", usecols=["eid", "sym", "ticker", "D", "E", "era"])
assert len(Q) == 269 and Q.E.max() < SEAL and Q.D.max() < SEAL
_t = pd.read_csv(f"{DATA}/cb702/qm_streams/holdings_1024/replay/trades.tsv.gz", sep="\t",
                 usecols=["eid", "arm", "in_window", "entry_status", "realized_r"])
_w = _t[(_t.arm == "d3_p33_tspd") & (_t.in_window == True) & (_t.entry_status == "filled")]  # noqa: E712
BIG_EIDS = set(_w[_w.realized_r >= 5].eid)
del _t, _w                                       # the label only; realized_r is never read again
Q["big"] = Q.eid.isin(BIG_EIDS)
Q["store_era"] = np.where(Q.D <= ERA_A_D_LAST, "A", "B")
assert int(Q.big.sum()) == 26, Q.big.sum()

# ═════════════════════════════════════════════════════════════════════════════════════════════════
# 1. The list (rules 1-7) from the feature table
# ═════════════════════════════════════════════════════════════════════════════════════════════════
COLS = ["scan_date", "E", "ticker", "era", "pass_history", "pass_universe", "pass_prior_move", "rs_best", "adr20",
        "prior_move", "prior_move.pole_high", "higher_lows.base_low", "close", "e21", "breakdown.sma50", "level"]
F = pd.concat([pd.read_parquet(f"{FEAT}/features_era{e}.parquet", columns=COLS) for e in "AB"], ignore_index=True)
assert F.scan_date.max() < SEAL and F.E.max() < SEAL
say("BLIND VERIFY of Stage 0 (Qullamaggie's 269 dated breakout buys are the scorecard; no returns; nothing >= 2025-01-01)")
say(f"feature rows {len(F):,}; nights {F.scan_date.nunique()} (A {F[F.era == 'A'].scan_date.nunique()}, B {F[F.era == 'B'].scan_date.nunique()}); "
    f"era of every row agrees with D<=2022-03-31: {bool(((F.scan_date <= ERA_A_D_LAST) == (F.era == 'A')).all())}")
key = pd.Series(F.index, index=pd.MultiIndex.from_arrays([F.ticker, F.scan_date]))
Q["row"] = [key.get((t, d)) for t, d in zip(Q.ticker, Q.D)]
say(f"Qullamaggie's buys joined to their night D in the table: {int(Q.row.notna().sum())}/269")
assert Q.row.notna().all()
Q["row"] = Q.row.astype(int)

depth = (F["prior_move.pole_high"] - F["higher_lows.base_low"]) / F["prior_move.pole_high"] / F.adr20
vs21 = (F.close / F.e21 - 1) / F.adr20
vs50 = F.close / F["breakdown.sma50"] - 1
RULES = {r["feature"]: r for r in json.load(open(f"{PARENT}/backward/12_final_rules.json"))["added_rules"]}
DHI, PM = RULES["base_depth_adr"]["hi"], RULES["prior_move"]["threshold"]
lrn = Q[(Q.sym == "LRN") & (Q.E == "2020-08-05")].row.iloc[0]
tsla = Q[(Q.sym == "TSLA") & (Q.E == "2022-04-21")].row.iloc[0]
DLO, T21 = float(depth[lrn]), float(vs21[tsla])
base = (F.pass_history == 1) & (F.pass_universe == 1) & (F.rs_best >= 35) & (F.adr20 >= 0.021) & (F.pass_prior_move == 1)
LIST = base & depth.between(DLO, DHI) & (F.prior_move >= PM) & (vs21 >= T21) & (vs50 >= 0)
ROUND = base & depth.between(1.5, 9.0) & (F.prior_move >= 0.321) & (vs21 >= -0.63) & (vs50 >= 0)
say(f"thresholds re-derived: depth lo = LRN 2020-08-05 {DLO:.4f}, hi {DHI:.4f} (12_final_rules.json), run-up >= {PM:.4f}, "
    f"close vs EMA21 >= TSLA 2022-04-21 {T21:.4f} ranges, close >= 50-day SMA")
NIGHTS = {"A": sorted(F.scan_date[F.era == "A"].unique()), "B": sorted(F.scan_date[F.era == "B"].unique())}
NIGHTS["ALL"] = NIGHTS["A"] + NIGHTS["B"]


def per_night(mask, nights):
    sub = mask[F.scan_date.isin(nights)]
    return sub.groupby(F.scan_date[sub.index]).sum().reindex(nights, fill_value=0)


def list_line(name, mask):
    n = per_night(mask, NIGHTS["ALL"])
    k = mask.loc[Q.row].values
    say(f"  {name:44s} Qullamaggie's buys on the list {int(k.sum())}/269 | big {int(k[Q.big.values].sum())}/26 | names a night "
        f"median {n.median():.0f} mean {n.mean():.0f} p90 {n.quantile(.9):.0f}")
    return k


say("\nLIST (rules 1-7):")
kl = list_line("exact derived thresholds (builder's)", LIST)
kr = list_line("spec's ROUNDED constants (1.5/9.0/32.1%/-0.63)", ROUND)
lost = Q[kl & ~kr]
say(f"  rounded constants drop {len(lost)} of Qullamaggie's on-list buys: " + ", ".join(f"{r.sym} {r.E} (vs EMA21 {vs21[r.row]:+.4f})" for r in lost.itertuples()))
out6 = Q[~kl]
say("  his 6 off the list: " + ", ".join(f"{r.sym} {r.E}" for r in out6.itertuples()))
Q["on_list"] = kl
flush_log()


# ═════════════════════════════════════════════════════════════════════════════════════════════════
# 2. Bar features from the daily stores (per ticker, on list rows only + every one of his 269)
# ═════════════════════════════════════════════════════════════════════════════════════════════════
def load_era_b_sealed():
    """cb702's daily export filtered to dates < SEAL line by line (date column only compared), in memory."""
    t0 = time.time()
    buf, kept, dropped = io.StringIO(), 0, 0
    with gzip.open(f"{CBD}/daily_closes_all.csv.gz", "rt") as fh:
        for ln in fh:
            if ln.split(",", 2)[1] >= SEAL:
                dropped += 1
                continue
            buf.write(ln)
            kept += 1
    buf.seek(0)
    D = runner.load_daily(buf)
    say(f"era-B sealed (in memory): kept {kept:,}, dropped {dropped:,} ({time.time() - t0:.0f}s); calendar {D.cal[0]}..{D.cal[-1]}")
    return D, kept


STORES = {}


def store(era):
    if era not in STORES:
        if era == "A":
            STORES["A"] = runner.load_daily(f"{PRE}/daily_closes_all.csv.gz")
        else:
            STORES["B"], _ = load_era_b_sealed()
        assert STORES[era].cal[-1].isoformat() < SEAL
    return STORES[era]


CACHE2 = f"{HERE}/_cache_barfeat.parquet"
if not os.path.exists(CACHE2):
    parts = []
    need = LIST.copy()
    need.loc[Q.row] = True                                   # every one of his 269 rows too
    for era in "AB":
        D = store(era)
        sub = F[need & (F.era == era)]
        t0 = time.time()
        for tk, grp in sub.groupby("ticker"):
            b, cidx = runner.bars_for(D, D.tid[tk])
            h, l, c, v = (np.asarray(x, float) for x in (b.h, b.l, b.c, b.v))
            H, L, C, V = pd.Series(h), pd.Series(l), pd.Series(c), pd.Series(v)
            lvl5 = H.rolling(5).max().values
            v10 = V.rolling(10).mean().values
            v50 = V.rolling(50).mean().values
            adr = ((H - L) / C).rolling(20).mean().values
            c10 = ((C.rolling(10).max() / C.rolling(10).min() - 1).values) / adr
            m126 = (H / L.rolling(64, min_periods=1).min() - 1).rolling(126, min_periods=1).max().values
            nb = len(h)
            pos = {d.isoformat(): i for i, d in enumerate(b.dates)}
            ii = np.array([pos[d] for d in grp.scan_date])
            nx = np.minimum(ii + 1, nb - 1)
            has = ii + 1 < nb
            parts.append(pd.DataFrame({
                "idx": grp.index.values, "bar_i": ii, "n_bars_to_D": ii + 1,
                "E_bar": [b.dates[j + 1].isoformat() if j + 1 < nb else None for j in ii],
                "c_D": c[ii], "lvl5": lvl5[ii], "adr_bar": adr[ii], "c10": c10[ii], "move126": m126[ii],
                "v10": v10[ii], "v50": v50[ii],
                "hE": np.where(has, h[nx], np.nan), "lE": np.where(has, l[nx], np.nan), "vE": np.where(has, v[nx], np.nan),
                "cal_gap_to_E": np.where(has, cidx[nx].astype(int) - cidx[ii].astype(int), -1)}))
        say(f"era {era}: bar features for {len(sub):,} rows / {sub.ticker.nunique():,} tickers in {time.time() - t0:.0f}s")
    pd.concat(parts, ignore_index=True).to_parquet(CACHE2, index=False)
B2 = pd.read_parquet(CACHE2).set_index("idx")
X = F.join(B2, how="inner")
X["up"] = X.hE > X.lvl5
X["x10"] = X.vE / X.v10
X["x50"] = X.vE / X.v50
X["Eok"] = X.E_bar == X.E
X["fire_new"] = X.up & (X.x10 >= 1.2) & X.Eok
X["fire_old"] = X.up & (X.x50 >= 1.2) & X.Eok
X["fire_px"] = X.up & X.Eok
X["on_list"] = LIST.reindex(X.index).values
say(f"\nbar-feature sanity on {int(X.on_list.sum()):,} list rows: close(D) store vs table max |diff| {float((X.c_D - X.close).abs()[X.on_list].max()):.2e}; "
    f"5-day high vs table level max |diff| {float((X.lvl5 - X.level).abs()[X.on_list].max()):.2e}; "
    f"ADR20 bars vs table max |diff| {float((X.adr_bar - X.adr20).abs()[X.on_list].max()):.2e}; "
    f"E = next stored session on {int(X.Eok[X.on_list].sum()):,} of {int(X.on_list.sum()):,} list rows")
QX = X.loc[Q.row]
say(f"Qullamaggie's 269: E is the next stored session {int(QX.Eok.sum())}/269; calendar gap D->E of exactly 1 session {int((QX.cal_gap_to_E == 1).sum())}/269")

# parity against the parent's era-A caches (comparison target only — never an input)
try:
    mv = pd.read_parquet(f"{FEAT}/move126_eraA.parquet").set_index("idx").move126
    tt = pd.read_parquet(f"{FEAT}/tight_recent_eraA.parquet").set_index("idx").c10
    tv = pd.read_parquet(f"{FEAT}/trigger_v10_eraA.parquet").set_index("idx")
    a = X[X.on_list & (X.era == "A")]
    d_mv = (a.move126 - mv.reindex(a.index)).abs().max()
    d_c10 = (a.c10 - tt.reindex(a.index)).abs().max()
    d_x10 = (a.x10 - tv.x10.reindex(a.index)).abs().max()
    d_x50 = (a.x50 - tv.x50.reindex(a.index)).abs().max()
    say(f"era-A parity vs the parent's caches (list rows {len(a):,}): move126 {d_mv:.2e}, c10 {d_c10:.2e}, x10 {d_x10:.2e}, x50 {d_x50:.2e}; "
        f"rows absent from the parent cache {int((~a.index.isin(tv.index)).sum())}, NaN x10 there (no E bar) {int(tv.x10.reindex(a.index).isna().sum())}")
except Exception as e:  # loud-ok: parity is a comparison only
    say(f"era-A parity vs the parent's caches: not run ({type(e).__name__}: {e})")
flush_log()

# ═════════════════════════════════════════════════════════════════════════════════════════════════
# 3. CHECK 2 — names a night, breakouts a day, his buys, big winners, the order score; per era and combined
# ═════════════════════════════════════════════════════════════════════════════════════════════════
LX = X[X.on_list].copy()
LX["mr"] = LX.move126 / LX.adr20
LX["p_run"] = LX.groupby("scan_date").mr.rank(pct=True)
LX["p_tight"] = LX.groupby("scan_date").c10.rank(pct=True, ascending=False)
LX["score"] = (LX.p_run + LX.p_tight) / 2
LX["night_rank"] = LX.groupby("scan_date").score.rank(ascending=False, method="first")
LX["night_n"] = LX.groupby("scan_date").score.transform("size")
say(f"\norder score: list rows with no score {int(LX.score.isna().sum())}")

# his labels (the merge logic of 32_tight_recently.py, re-typed)
symtk = dict(zip(Q.sym, Q.ticker))
fkey = {(t, d): i for i, t, d in zip(F.index, F.ticker, F.scan_date)}
L1 = pd.read_csv(f"{PARENT}/27_loose_wide_labels.tsv", sep="\t")[["who", "sym", "D", "label", "yes"]]
L2 = pd.read_csv(f"{PARENT}/31_tight3_labels.tsv", sep="\t")
L2 = pd.DataFrame({"who": "QM buy", "sym": L2.sym, "D": L2.D, "label": L2.his,
                   "yes": L2.his.str.startswith(("ok", "good")) | L2.his.str.contains("earlier") & ~L2.his.str.startswith("no")})
L2.loc[L2.label.str.startswith("no") | L2.label.str.contains("EP"), "yes"] = False
LAB = pd.concat([L1[~L1.set_index(["sym", "D"]).index.isin(L2.set_index(["sym", "D"]).index)], L2])
LAB["i"] = [fkey.get((symtk.get(s, s) if w == "QM buy" else s, d)) for s, d, w in zip(LAB.sym, LAB.D, LAB.who)]
LAB = LAB[LAB.i.notna()]
LAB["i"] = LAB.i.astype(int)


def auc_on(idx_set):
    s = LX.score
    yy = [i for i in LAB[LAB.yes].i if i in s.index and i in idx_set]
    nn = [i for i in LAB[~LAB.yes].i if i in s.index and i in idx_set]
    if not yy or not nn:
        return float("nan"), len(yy), len(nn)
    return float(np.mean([[1.0 if s[u] > s[v] else (0.5 if s[u] == s[v] else 0.0) for v in nn] for u in yy])), len(yy), len(nn)


RES = {}
for era in ("A", "B", "ALL"):
    nights = NIGHTS[era]
    lst = per_night(LIST, nights)
    sub = LX[LX.scan_date.isin(nights)]
    fn = sub.fire_new.groupby(sub.scan_date).sum().reindex(nights, fill_value=0)
    fo = sub.fire_old.groupby(sub.scan_date).sum().reindex(nights, fill_value=0)
    q = Q if era == "ALL" else Q[Q.store_era == era]
    qo = q[q.on_list]
    qf_new = LX.fire_new.reindex(qo.row).fillna(False).values
    qf_old = LX.fire_old.reindex(qo.row).fillna(False).values
    rk = LX.night_rank.reindex(qo.row).values
    big = qo.big.values
    a, ny, nn = auc_on(set(sub.index))
    RES[era] = dict(nights=len(nights), list_med=lst.median(), list_mean=lst.mean(), list_p90=lst.quantile(.9),
                    new_med=fn.median(), new_mean=fn.mean(), new_p90=fn.quantile(.9), new_gt5=int((fn > 5).sum()), new_0=int((fn == 0).sum()),
                    old_med=fo.median(), old_mean=fo.mean(), old_p90=fo.quantile(.9), old_gt5=int((fo > 5).sum()), old_0=int((fo == 0).sum()),
                    q_n=len(q), q_on=len(qo), q_new=int(qf_new.sum()), q_old=int(qf_old.sum()), big_n=int(q.big.sum()), big_on=int(big.sum()),
                    big_new=int(qf_new[big].sum()), big_old=int(qf_old[big].sum()),
                    top10=int((rk <= 10).sum()), top20=int((rk <= 20).sum()), top30=int((rk <= 30).sum()), top50=int((rk <= 50).sum()),
                    big_top20=int((rk[big] <= 20).sum()), big_top50=int((rk[big] <= 50).sum()), auc=a, auc_y=ny, auc_n=nn)
    r = RES[era]
    say(f"\nCHECK 2 — era {era}: {r['nights']} nights ({nights[0]} .. {nights[-1]})")
    say(f"  list: names a night median {r['list_med']:.0f}, mean {r['list_mean']:.1f}, p90 {r['list_p90']:.0f} | Qullamaggie's buys on the list {r['q_on']}/{r['q_n']} | big {r['big_on']}/{r['big_n']}")
    say(f"  NEW 1.2x 10-day: breakouts a day median {r['new_med']:.0f}, mean {r['new_mean']:.1f}, p90 {r['new_p90']:.0f}; days >5 {r['new_gt5']} ({r['new_gt5'] / r['nights']:.0%}), days 0 {r['new_0']} | his firing on E {r['q_new']}/{r['q_on']} | big {r['big_new']}/{r['big_on']}")
    say(f"  OLD 1.2x 50-day: breakouts a day median {r['old_med']:.0f}, mean {r['old_mean']:.1f}, p90 {r['old_p90']:.0f}; days >5 {r['old_gt5']} ({r['old_gt5'] / r['nights']:.0%}), days 0 {r['old_0']} | his firing on E {r['q_old']}/{r['q_on']} | big {r['big_old']}/{r['big_on']}")
    say(f"  order score: yes-above-no {r['auc']:.2f} (yes {r['auc_y']}, no {r['auc_n']}) | his buys in their night's top 10 {r['top10']}, top 20 {r['top20']}, top 30 {r['top30']}, top 50 {r['top50']} of {r['q_on']} | big top 20 {r['big_top20']}, top 50 {r['big_top50']}")

# era-B one by one (the builder lists these) + the truncated look-back
qb = Q[Q.store_era == "B"]
say("\n  era-B buys one by one:")
for r in qb.itertuples():
    x = X.loc[r.row]
    say(f"    {r.sym:5s} buy {r.E} on list {'yes' if r.on_list else 'NO '} | NEW {'yes' if x.fire_new else 'no '} OLD {'yes' if x.fire_old else 'no '} | "
        f"high>5d {'y' if x.up else 'n'} x10 {x.x10:.2f} x50 {x.x50:.2f} | move126 {x.move126:.0%} = {x.move126 / x.adr20:.1f} ranges c10 {x.c10:.1f} | "
        f"night rank {LX.night_rank.get(r.row, np.nan):.0f} of {LX.night_n.get(r.row, np.nan):.0f}")
DBs = store("B")
first_b = DBs.cal[0]
eb_n = NIGHTS["B"]
cal_b = [d.isoformat() for d in DBs.cal]
short = [d for d in eb_n if cal_b.index(d) + 1 < 126 + 63]     # fewer than 126 + 63 sessions of store before the night
say(f"  (the builder's count uses index < 189, i.e. it also counts the night whose window starts exactly on the store's first bar)")
say(f"  era-B store starts {first_b}; nights whose 6-month move window (126 sessions + the 64-session low) reaches before it: {len(short)} (to {short[-1] if short else '-'})")
short126 = [d for d in eb_n if cal_b.index(d) + 1 < 126]
say(f"  era-B nights with fewer than 126 sessions of store history: {len(short126)}")
flush_log()

# ═════════════════════════════════════════════════════════════════════════════════════════════════
# 4. CHECK 3 — each day's firing names (NEW), ranked by the score over the night's whole list
# ═════════════════════════════════════════════════════════════════════════════════════════════════
FI = LX[LX.fire_new].copy()
FI["fire_rank"] = FI.groupby("scan_date").score.rank(ascending=False, method="first")
FI["fire_n"] = FI.groupby("scan_date").score.transform("size")
FI["fire_rank_min"] = FI.groupby("scan_date").score.rank(ascending=False, method="min")
say(f"\nCHECK 3 — firing name-days {len(FI):,}; with no score {int(FI.score.isna().sum())}")
for era in ("A", "B", "ALL"):
    q = Q if era == "ALL" else Q[Q.store_era == era]
    qo = q[q.on_list]
    hit = qo[qo.row.isin(FI.index)]
    rk = FI.fire_rank.reindex(hit.row).values
    rkm = FI.fire_rank_min.reindex(hit.row).values
    bg = hit.big.values
    say(f"  era {era}: his firing {len(hit)} of {len(qo)} on the list -> top 5 {int((rk <= 5).sum())}, top 10 {int((rk <= 10).sum())} "
        f"(ties as min: {int((rkm <= 5).sum())}/{int((rkm <= 10).sum())}) | big firing {int(bg.sum())} -> top 5 {int((rk[bg] <= 5).sum())}, top 10 {int((rk[bg] <= 10).sum())}")
    if era == "ALL":
        say(f"  his firing buys' rank: median {np.median(rk):.0f}, quartiles {np.percentile(rk, 25):.0f}-{np.percentile(rk, 75):.0f}; "
            f"their day's firing count median {np.median(FI.fire_n.reindex(hit.row).values):.0f}")
        bh = hit[hit.big]
        say("  big winners that fire (rank of firing): " + ", ".join(
            f"{r.sym} {r.E} #{FI.fire_rank[r.row]:.0f}/{FI.fire_n[r.row]:.0f}" for r in bh.sort_values("E").itertuples()))
flush_log()


# ═════════════════════════════════════════════════════════════════════════════════════════════════
# 5. CHECK 1 — the intraday buy on his buy day E (my own tick loop around the live pure functions)
# ═════════════════════════════════════════════════════════════════════════════════════════════════
MINUTE_DIRS = [f"{PRE}/minutes", f"{CBD}/minutes", f"{CBD}/minutes_asis_1026", f"{CBD}/minutes_rev_1024",
               f"{CBD}/minutes_intra_1025", f"{CBD}/minutes_ep_1023", f"{CBD}/minutes_ep_1024",
               f"{CBD}/minutes_com_delta_1018", f"{CBD}/minutes_pre_com_1018", f"{CBD}/cb702_minutes_delta_out",
               f"{CBD}/minutes_bv1_1101"]
DONE = {}
for d in MINUTE_DIRS:
    p = f"{d}/_done.psv"
    if os.path.exists(p):
        dd = {}
        for ln in open(p).read().splitlines():
            f_ = ln.split("|")
            if len(f_) >= 4 and f_[0] < SEAL:
                dd[(f_[0], f_[1])] = f_[3]
        DONE[d] = dd


def held(e, tk):
    for d in MINUTE_DIRS:
        if DONE.get(d, {}).get((e, tk)) in ("ok", "empty") and os.path.exists(f"{d}/{e}.psv.gz"):
            return d
    return None


_MCACHE = {}


def minute_rows(d, e, tk):
    assert e < SEAL
    k = (d, e)
    if k not in _MCACHE:
        rows = {}
        with gzip.open(f"{d}/{e}.psv.gz", "rt") as fh:
            for ln in fh:
                f_ = ln.rstrip("\n").split("|")
                rows.setdefault(f_[0], []).append(f_)
        _MCACHE.clear()
        _MCACHE[k] = rows
    out = {}
    for f_ in _MCACHE[k].get(tk, []):
        m = int(f_[1])
        out[m] = {"open": float(f_[2]), "high": float(f_[3]), "low": float(f_[4]), "close": float(f_[5]), "volume": float(f_[6])}
    return out


VOL_CURVE_REASON = bve.SETUP_BREAKOUT_VOLUME_BELOW_CURVE
WIDE = bve.SETUP_STOP_TOO_WIDE


def sim_live(mins_all, *, list_level, adr20, vol_bar, literal=False):
    """One list name on E, tick by tick, as breakout_v1_entry.run_breakout_v1_entry_tick does it.
    Tick m (09:35 = 5 .. 15:55 = 385) reads the bars through m-1 (live: bars_by_minute(..., last_completed=m-1)),
    decides, then bar m prints and a resting order may fill. Live paths modelled:
      no row:  evaluate -> wait | abstain (terminal) | volume hold | place via submit_trade_entry ->
               prepare_breakout_order (width_at_expected_fill at max(level, latest x 1.002)) -> submit_entry
               (#500: latest > level -> limit latest x 1.002, chase cap 1.5x planned -> cancelled)
      a row:   _manage: _terminal_reason (EOD / abstain / F1 lapse) -> cancel; a new day low below the placed stop
               -> cancel + _replace (width_at_expected_fill again, then submit_entry again: #500 + chase cap with the
               NEW stop, on the latest price) — a triggered-but-unfilled stop-limit is re-placed the same way.
      fill:    one minute later the stop at the fill (stop_at_fill_decision on the true low through the fill minute).
    'latest' (live: get_latest_trade during minute m) = the close of the last completed bar. literal=True: an F1
    lapse never cancels a live order (the rule read literally)."""
    tr = {"outcome": None, "reason": None, "placed_m": None, "kind": None, "fill": None, "fill_m": None, "reprices": 0,
          "replace_kind_change": 0, "holds": 0, "first_f1_m": None, "stop": None}
    order = None
    mins = {}
    for m in range(bve.FIRST_MINUTE, bve.EOD_MINUTE + 1):
        lc = m - 1
        for k in (range(0, lc + 1) if m == bve.FIRST_MINUTE else (lc,)):
            if k in mins_all:
                mins[k] = mins_all[k]
        if tr["fill_m"] is not None:
            if m == tr["fill_m"] + 1:
                tl = min(b["low"] for mm, b in mins_all.items() if mm <= tr["fill_m"])
                dec = bve.stop_at_fill_decision(fill=tr["fill"], true_low=tl, adr20=adr20, placed_stop=order["stop"])
                tr["stop_check"] = dec["action"]
                if dec["action"] == "sell_all":
                    tr.update(outcome="sold_after_fill", reason=dec["reason"])
                return tr
            continue
        st = bve.evaluate(mins, list_level=float(list_level), adr20=adr20, vol_bar=float(vol_bar), last_completed=lc)
        if st["status"] == "ok" and st["f1_ok"] and tr["first_f1_m"] is None:
            tr["first_f1_m"] = lc
        latest = mins[max(mins)]["close"] if mins else None
        if order is None:
            if m >= bve.EOD_MINUTE:
                tr.update(outcome="never_placed", reason="pace_never_met")
                return tr
            if st["status"] == "wait":
                continue
            if st["status"] == "abstain":
                tr.update(outcome="abstain", reason=st["reason"])
                return tr
            if not st["f1_ok"]:
                tr["holds"] += 1
                continue
            o = place(st["level"], st["stop"], latest, adr20)
            if isinstance(o, str):
                tr.update(outcome="abstain", reason=o)
                return tr
            order = o
            tr.update(placed_m=m, kind=o["kind"])
        else:
            reason = bve._terminal_reason(st, m)
            if literal and reason is not None and reason.startswith(VOL_CURVE_REASON):
                reason = None
            if reason is not None:
                tr.update(outcome="cancelled", reason=reason)
                return tr
            if st["status"] == "ok" and st["stop"] < order["stop"] - bve.STOP_EPS:
                # _manage -> _cancel_and_confirm -> _replace(level = row orb_high = the order's level, the new stop)
                o = place(order["level"], st["stop"], latest, adr20)
                tr["reprices"] += 1
                if isinstance(o, str):
                    tr.update(outcome="cancelled", reason="replace: " + o)
                    return tr
                if o["kind"] != order["kind"] or order.get("triggered"):
                    tr["replace_kind_change"] += 1
                order = o
        bar = mins_all.get(m)
        if bar is None:
            continue
        op, hi, lo = bar["open"], bar["high"], bar["low"]
        fill = None
        if order["kind"] == "stop_limit" and not order["triggered"]:
            if hi >= order["level"]:
                order["triggered"] = True
                if op <= order["level"]:
                    fill = order["level"]
                elif op <= order["limit"]:
                    fill = op
                elif lo <= order["limit"]:
                    fill = order["limit"]
        else:
            if op <= order["limit"]:
                fill = op
            elif lo <= order["limit"]:
                fill = order["limit"]
        if fill is not None:
            tr.update(outcome="filled", fill=float(fill), fill_m=m, stop=order["stop"])
    if tr["fill_m"] is not None:
        tr["stop_check"] = "unchecked_eod"
        return tr
    if order is not None:
        tr.update(outcome="cancelled", reason=f"{bve.WINDOW_BREAKOUT_UNFILLED_EOD}: unfilled at 15:55 ET")
        return tr
    tr.update(outcome="never_placed", reason="pace_never_met")
    return tr


def place(level, stop, latest, adr20):
    """prepare_breakout_order's width rule at the expected fill, then submit_entry's #500 pick + chase cap. -> order or reason."""
    if stop >= level:
        return "setup:zero_range"
    fill = level if latest is None or latest <= level else round(latest * 1.002, 2)
    if adr20 is None or not adr20 > 0 or (fill - stop) / fill > adr20:
        return "fallback_width" if fill > level else "setup:stop_too_wide (at placement)"
    if latest is not None and latest > level:
        lim = round(latest * 1.002, 2)
        if not ((level - stop) > 0 and (lim - stop) <= CHASE_RISK_INFLATION_CAP * (level - stop)):
            return "chase_cap"
        return {"kind": "limit", "level": level, "limit": lim, "stop": stop, "triggered": True}
    return {"kind": "stop_limit", "level": level, "limit": stop_limit_buy_price(level), "stop": stop, "triggered": False}


def why(tr):
    o, r = tr["outcome"], str(tr["reason"] or "")
    if o in ("filled", "sold_after_fill"):
        return "bought"
    if "fallback_width" in r or "chase_cap" in r:
        return "#500 fallback chase cap / width"
    if WIDE in r:
        return "stop too wide"
    if r.startswith(VOL_CURVE_REASON):
        return "pace lapsed, cancelled"
    if o == "never_placed":
        return "pace never met"
    if r.startswith(bve.WINDOW_BREAKOUT_UNFILLED_EOD):
        return "never reached the level"
    return r[:48] or o


def permits_string(mins_all, vol_bar):
    """'1'/'0' per last-completed minute 0..389: F1 (cum volume through lc >= vol_bar x CUM_SHARE[lc]), price ignored."""
    cum, out = 0.0, []
    for lc in range(390):
        cum += mins_all.get(lc, {}).get("volume", 0.0)
        out.append("1" if bve.f1_permits(cum, vol_bar, lc)[0] else "0")
    return "".join(out)


rows1 = []
cov = Counter()
rev_hits = {"ticker": 0, "sym": 0}
t0 = time.time()
for r in Q.itertuples():
    for kk, tk in (("ticker", r.ticker), ("sym", r.sym)):
        if DONE.get(f"{CBD}/minutes_rev_1024", {}).get((r.E, tk)) in ("ok", "empty"):
            rev_hits[kk] += 1
    d = held(r.E, r.ticker)
    used_key = "ticker"
    if d is None and r.sym != r.ticker:
        d, used_key = held(r.E, r.sym), "sym"
    rec = {"eid": r.eid, "sym": r.sym, "ticker": r.ticker, "D": r.D, "E": r.E, "era": r.store_era, "big": r.big,
           "on_list": r.on_list, "store": os.path.basename(d) if d else None, "key": used_key}
    if d is None:
        cov["not held"] += 1
        rows1.append(rec)
        continue
    cov[os.path.basename(os.path.dirname(d)) + "/" + os.path.basename(d)] += 1
    mins = minute_rows(d, r.E, r.ticker if used_key == "ticker" else r.sym)
    x = X.loc[r.row]
    dh, dl = x.hE, x.lE
    if not mins:
        rec["minutes"] = "no_rows"
        rows1.append(rec)
        continue
    mh, ml = max(b["high"] for b in mins.values()), min(b["low"] for b in mins.values())
    rec.update(minutes="ok", mm_hi=abs(mh - dh) / dh, mm_lo=abs(ml - dl) / dl,
               rth_share=sum(b["volume"] for b in mins.values()) / x.vE, n_min=len(mins))
    rec["mismatch"] = bool(rec["mm_hi"] > 0.01 or rec["mm_lo"] > 0.01)
    lvl, adr, vb_old, vb_new = float(x.lvl5), float(x.adr20), 1.2 * float(x.v50), 1.2 * float(x.v10)
    rec.update(level=lvl, adr20=adr, level_eq_table=bool(abs(lvl - x.level) < 1e-9))
    for name, vb in (("px", 0.0), ("old", vb_old), ("new", vb_new)):
        for lit in (False, True):
            tr = sim_live(mins, list_level=lvl, adr20=adr, vol_bar=vb, literal=lit)
            tag = name + ("_lit" if lit else "")
            rec[f"{tag}_out"] = tr["outcome"]
            rec[f"{tag}_why"] = why(tr)
            rec[f"{tag}_fm"] = tr["fill_m"]
            rec[f"{tag}_reprices"] = tr["reprices"]
            rec[f"{tag}_kindchg"] = tr["replace_kind_change"]
            rec[f"{tag}_kind"] = tr["kind"]
            rec[f"{tag}_f1m"] = tr["first_f1_m"]
            rec[f"{tag}_placed"] = tr["placed_m"]
            pm = tr["placed_m"]
            rec[f"{tag}_open_at_place"] = mins[pm]["open"] if pm is not None and pm in mins else np.nan
            rec[f"{tag}_close_before_place"] = mins[max(k for k in mins if k < pm)]["close"] if pm is not None and any(k < pm for k in mins) else np.nan
    for name, vb in (("old", vb_old), ("new", vb_new)):          # the builder's LITERAL, re-typed from s0_check1.py (read AFTER my run)
        got, cur = None, {}
        for m in range(bve.FIRST_MINUTE, bve.EOD_MINUTE):
            for k in (range(0, m) if m == bve.FIRST_MINUTE else (m - 1,)):
                if k in mins:
                    cur[k] = mins[k]
            st = bve.evaluate(cur, list_level=lvl, adr20=adr, vol_bar=vb, last_completed=m - 1)
            if st["status"] == "ok" and st["f1_ok"] and m in mins and mins[m]["high"] >= st["level"]:
                got = m
                break
        rec[f"blit_{name}"] = got is not None
    rec["perm_old"] = permits_string(mins, vb_old)
    rec["perm_new"] = permits_string(mins, vb_new)
    # the daily-bar test on E for the same buy
    rec["daily_new"] = bool(x.fire_new)
    rec["up_daily"] = bool(x.up)
    rec["daily_old"] = bool(x.fire_old)
    rec["x10_full"] = float(x.x10)
    rec["orh5"] = max(mins[m]["high"] for m in mins if m < 5) if any(m < 5 for m in mins) else np.nan
    rows1.append(rec)
C1 = pd.DataFrame(rows1)
C1.to_csv(f"{HERE}/verify_check1_buys.tsv", sep="\t", index=False)
say(f"\nCHECK 1 — the intraday buy on Qullamaggie's buy day E ({time.time() - t0:.0f}s)")
say(f"  named store minutes_rev_1024 holds his (E, ticker) pairs: by ticker {rev_hits['ticker']}, by sym {rev_hits['sym']} of 269")
say(f"  covered through the sealed minute stores (precedence order): {dict(cov)}; key used: {dict(Counter(C1.key[C1.store.notna()]))}")
ok = C1[C1.minutes == "ok"]
say(f"  minute rows ok {len(ok)}; minute-vs-daily high/low off by > 1%: {int(ok.mismatch.sum())} "
    f"(max hi {ok.mm_hi.max():.4f}, max lo {ok.mm_lo.max():.4f}); level = table v1 level {int(ok.level_eq_table.sum())}/{len(ok)}")
say(f"  regular-hours minute volume / full daily volume: median {ok.rth_share.median():.2f} (CUM_SHARE[389] = {bve.CUM_SHARE[389]:.4f})")
R1 = ok[~ok.mismatch]


def bought(df, tag):
    return df[f"{tag}_out"].isin(["filled", "sold_after_fill"])


def fm_line(df, tag):
    b = df[bought(df, tag)][f"{tag}_fm"].astype(int)
    return (f"bought {len(b)}: median {clock(np.median(b))}, quartiles {clock(np.percentile(b, 25))}-{clock(np.percentile(b, 75))}, "
            f"by 09:45 {int((b <= 15).sum())}, by 10:00 {int((b <= 30).sum())}, by 10:30 {int((b <= 60).sum())}, after 12:00 {int((b > 150).sum())}")


groups = {"all covered": R1, "on the list": R1[R1.on_list], "era A on list": R1[R1.on_list & (R1.era == "A")],
          "era B on list": R1[R1.on_list & (R1.era == "B")], "big winners": R1[R1.big]}
for g, df in groups.items():
    say(f"  {g:14s} n={len(df):3d} | price only {int(bought(df, 'px').sum())} | OLD {int(bought(df, 'old').sum())} | NEW {int(bought(df, 'new').sum())} || "
        f"literal OLD {int(bought(df, 'old_lit').sum())}, NEW {int(bought(df, 'new_lit').sum())} || daily OLD {int(df.daily_old.sum())}, NEW {int(df.daily_new.sum())} || "
        f"sold-after-fill NEW {int((df.new_out == 'sold_after_fill').sum())}")
ol = R1[R1.on_list]
for tag in ("px", "old", "new"):
    say(f"  {tag:3s} on list  {fm_line(ol, tag)}")
    say(f"  {tag:3s} big      {fm_line(R1[R1.big], tag)}")
for tag in ("px", "old", "new"):
    say(f"  why not bought ({tag}, on list): " + ", ".join(f"{k} {v}" for k, v in Counter(ol[f"{tag}_why"]).most_common()))
say("  why not bought (NEW, big): " + ", ".join(f"{k} {v}" for k, v in Counter(R1[R1.big].new_why).most_common()))
bi = bought(ol, "new").values
dn = ol.daily_new.values
say(f"  NEW intraday vs NEW daily (on list): both {int((bi & dn).sum())}, intraday only {int((bi & ~dn).sum())}, daily only {int((~bi & dn).sum())}, neither {int((~bi & ~dn).sum())}")
do = ol[~bi & dn]
say("    daily only, why not bought live: " + ", ".join(f"{k} {v}" for k, v in Counter(do.new_why).most_common()))
io_ = ol[bi & ~dn]
say(f"    intraday only: full-day volume under 1.2x the 10-day {int((io_.x10_full < 1.2).sum())} of {len(io_)} (median {io_.x10_full.median():.2f}x)")
bb = R1[R1.big]
bbi, bbd = bought(bb, "new").values, bb.daily_new.values
say(f"  big NEW intraday vs daily: both {int((bbi & bbd).sum())}, intraday only {int((bbi & ~bbd).sum())} "
    f"({', '.join(f'{r.sym} {r.E}' for r in bb[bbi & ~bbd].itertuples())}), daily only {int((~bbi & bbd).sum())}, neither {int((~bbi & ~bbd).sum())}")
say("  big winners not bought under NEW: " + "; ".join(f"{r.sym} {r.E} ({r.new_why})" for r in bb[~bbi].sort_values("E").itertuples()))
px_nr = ol[ol.px_why == "never reached the level"]
px_orh = px_nr[(px_nr.orh5 > px_nr.level)]
say(f"  price-only 'never reached': {len(px_nr)}, of which the 5-minute opening-range high sat above the 5-day level: {len(px_orh)} "
    f"({', '.join(f'{r.sym} {r.E}' for r in px_orh.itertuples())})")
rp = R1[(R1.new_reprices > 0)]
say(f"  re-prices (NEW): {len(rp)} buys re-priced at least once; re-price that changed the order kind or replaced a TRIGGERED stop-limit: "
    f"{int((R1.new_kindchg > 0).sum())} ({', '.join(f'{r.sym} {r.E}' for r in R1[R1.new_kindchg > 0].itertuples())})")
say(f"  NEW orders placed as the #500 limit (price already past the level at placement): {int((R1.new_kind == 'limit').sum())}")
for tag in ("old", "new"):
    b = R1[bought(R1, tag) & (R1[f"{tag}_kind"] == "stop_limit")]
    gap = b[b[f"{tag}_open_at_place"] > np.maximum(b.orh5, b.level)]          # the ORDER level = max(ORH5, list level)
    same = b[b[f"{tag}_fm"] == b[f"{tag}_placed"]]
    say(f"  {tag.upper()} bought via a stop-limit: {len(b)}; filled in the placement minute itself {len(same)}; the placement minute OPENED above the level "
        f"(live's latest trade at the tick would read past the level -> #500 limit + chase cap, or a venue-killed stop if the last trade lagged the ask) {len(gap)}: "
        + ", ".join(f"{r.sym} {r.E}" for r in gap.itertuples()))
fb = ol[ol.new_why == "#500 fallback chase cap / width"]
say(f"  NEW #500-fallback misses on the list: {len(fb)}; under price-only those were: {dict(Counter(fb.px_why))}; volume holds before placement (NEW): "
    f"{int((fb.new_f1m.isna() | (fb.new_f1m > 4)).sum())} placed after 09:35")
nr16 = ol[ol.px_why == "never reached the level"]
say(f"  price-only 'never reached' {len(nr16)}: daily high above the 5-day high {int(nr16.up_daily.sum()) if 'up_daily' in nr16 else 'n/a'}")
say(f"  RTH minute volume / full daily volume on his 269 buy days: mean {ok.rth_share.mean():.3f}, median {ok.rth_share.median():.3f}; "
    f"era A median {ok[ok.era == 'A'].rth_share.median():.3f}, era B median {ok[ok.era == 'B'].rth_share.median():.3f}; share >= 0.8035 on {int((ok.rth_share >= 0.8035).sum())}/{len(ok)}")
flush_log()

# his buy time (first stream frame showing the position on E)
ent = pd.read_csv(f"{DATA}/cb702/qm_streams/holdings_1024/entries.tsv", sep="\t", usecols=["eid", "first_clock_on_E"])
C1 = C1.merge(ent, on="eid", how="left")
R1 = R1.merge(ent, on="eid", how="left")
hb = R1[R1.on_list & R1.first_clock_on_E.notna()].copy()
hb["sm"] = [int(c[:2]) * 60 + int(c[3:5]) - 570 for c in hb.first_clock_on_E]
say(f"\n  his buy time: {len(hb)} on-list buys with a first-sighting clock on E; median {clock(hb.sm.median())}, by 10:00 {int((hb.sm <= 30).sum())}, before 09:35 {int((hb.sm < 5).sum())}")
for tag in ("old", "new"):
    met = (hb[f"{tag}_f1m"].notna() & (hb[f"{tag}_f1m"] <= hb.sm - 1))
    at = pd.Series([sm >= 5 and p[sm - 1] == "1" for sm, p in zip(hb.sm, hb[f"perm_{tag}"])], index=hb.index)
    ever = pd.Series([sm >= 5 and "1" in p[4:sm] for sm, p in zip(hb.sm, hb[f"perm_{tag}"])], index=hb.index)
    say(f"  {tag}: volume pace (price ignored) met AT the minute before his sighting {int(at.sum())}/{len(hb)}, met at ANY tick up to it {int(ever.sum())}/{len(hb)}")
    bt = bought(hb, tag) & (hb[f"{tag}_fm"] <= hb.sm)
    later = bought(hb, tag) & (hb[f"{tag}_fm"] > hb.sm)
    say(f"  {tag}: F1 permitted (with the price setup ok) at some tick reading through the minute before his sighting {int(met.sum())}/{len(hb)} | "
        f"our replay bought at or before his sighting {int(bt.sum())}, later {int(later.sum())}, not at all {int((~bought(hb, tag)).sum())}")
flush_log()

# the required sample: all covered big winners + a seed-1103 random 20 of the rest
rest = sorted(R1[~R1.big].eid.tolist())
random.seed(1103)
samp = set(R1[R1.big].eid) | set(random.sample(rest, 20))
S = R1[R1.eid.isin(samp)].sort_values(["big", "E"], ascending=[False, True])
say(f"\n  PER-BUY SAMPLE ({len(S)} = {int(S.big.sum())} big winners + 20 random, seed 1103): OLD vs NEW decision and minute")
for r in S.itertuples():
    say(f"    {'BIG ' if r.big else '    '}{r.sym:5s} {r.E} list {'y' if r.on_list else 'n'} | OLD {r.old_why:31s} {clock(r.old_fm):5s} | "
        f"NEW {r.new_why:31s} {clock(r.new_fm):5s} | daily OLD {'y' if r.daily_old else 'n'} NEW {'y' if r.daily_new else 'n'}")
flush_log()

# ═════════════════════════════════════════════════════════════════════════════════════════════════
# 6. Cross-check: the builder's stated engine (v1_replay.simulate_entry) on the SAME inputs, per buy
# ═════════════════════════════════════════════════════════════════════════════════════════════════
os.environ.setdefault("BV1_SCRATCH", f"{HERE}/_scratch_unused")
sys.path.insert(0, f"{REPO}/scripts/probes/_breakout_v1_replay_1101")
import v1_replay as VR  # noqa: E402

assert [str(p) for p in VR.MINUTE_DIRS] == MINUTE_DIRS, "minute-store precedence differs from v1_replay.MINUTE_DIRS"
diffs = []
agree = Counter()
for r in R1.itertuples():
    d = held(r.E, r.ticker) or held(r.E, r.sym)
    mins = minute_rows(d, r.E, r.ticker if held(r.E, r.ticker) else r.sym)
    x = X.loc[Q.row[Q.eid == r.eid].iloc[0]]
    for tag, vb in (("old", 1.2 * float(x.v50)), ("new", 1.2 * float(x.v10)), ("px", 0.0)):
        t = VR.simulate_entry(mins, list_level=float(x.lvl5), adr20=float(x.adr20), vol_bar=vb)
        theirs_b = t["outcome"] in ("filled", "sold_after_fill")
        mine_b = getattr(r, f"{tag}_out") in ("filled", "sold_after_fill")
        same = theirs_b == mine_b and (not mine_b or t["fill_minute"] == getattr(r, f"{tag}_fm"))
        agree[(tag, same)] += 1
        if not same:
            diffs.append(f"{tag} {r.sym} {r.E}: mine {getattr(r, f'{tag}_why')} {clock(getattr(r, f'{tag}_fm'))} | v1_replay {t['outcome']} {t['reason']} {clock(t['fill_minute'])}")
say(f"\nCROSS-CHECK my live-path loop vs v1_replay.simulate_entry (same inputs): agree {dict(agree)}")
for s in diffs[:40]:
    say("    " + s)
VR_COUNTS = {}
flush_log()

# ═════════════════════════════════════════════════════════════════════════════════════════════════
# 6b. My numbers next to the builder's claims (stage0/s0.txt), MATCH / DIFF
# ═════════════════════════════════════════════════════════════════════════════════════════════════
olst = R1[R1.on_list]
M = {
    "c1 store minutes_rev_1024 holds": rev_hits["ticker"], "c1 covered pre_v2": cov.get("cb702_pre_v2/minutes", 0),
    "c1 covered cb702": cov.get("cb702/minutes", 0), "c1 mismatch excluded": int(ok.mismatch.sum()),
    "c1 OLD on list": int(bought(olst, "old").sum()), "c1 NEW on list": int(bought(olst, "new").sum()),
    "c1 px on list": int(bought(olst, "px").sum()),
    "c1 OLD era A": int(bought(olst[olst.era == "A"], "old").sum()), "c1 NEW era A": int(bought(olst[olst.era == "A"], "new").sum()),
    "c1 OLD era B": int(bought(olst[olst.era == "B"], "old").sum()), "c1 NEW era B": int(bought(olst[olst.era == "B"], "new").sum()),
    "c1 OLD big": int(bought(R1[R1.big], "old").sum()), "c1 NEW big": int(bought(R1[R1.big], "new").sum()),
    "c1 px big": int(bought(R1[R1.big], "px").sum()),
    "c1 literal(no-lapse-cancel, #500 kept) OLD on list": int(bought(olst, "old_lit").sum()),
    "c1 literal(no-lapse-cancel, #500 kept) NEW on list": int(bought(olst, "new_lit").sum()),
    "c1 literal(no-lapse-cancel, #500 kept) OLD big": int(bought(R1[R1.big], "old_lit").sum()),
    "c1 literal(no-lapse-cancel, #500 kept) NEW big": int(bought(R1[R1.big], "new_lit").sum()),
    "c2 B list median": RES["B"]["list_med"], "c2 B list mean": round(RES["B"]["list_mean"]), "c2 B list p90": round(RES["B"]["list_p90"]),
    "c2 B NEW median": RES["B"]["new_med"], "c2 B NEW mean": round(RES["B"]["new_mean"], 1), "c2 B NEW p90": RES["B"]["new_p90"],
    "c2 B NEW days>5": RES["B"]["new_gt5"], "c2 B OLD median": RES["B"]["old_med"], "c2 B OLD mean": round(RES["B"]["old_mean"], 1),
    "c2 B on list": RES["B"]["q_on"], "c2 B fire NEW": RES["B"]["q_new"], "c2 B fire OLD": RES["B"]["q_old"],
    "c2 B top10/20/30/50": (RES["B"]["top10"], RES["B"]["top20"], RES["B"]["top30"], RES["B"]["top50"]),
    "c2 ALL list med/mean/p90": (RES["ALL"]["list_med"], round(RES["ALL"]["list_mean"]), round(RES["ALL"]["list_p90"])),
    "c2 ALL NEW med/mean/p90": (RES["ALL"]["new_med"], round(RES["ALL"]["new_mean"], 1), round(RES["ALL"]["new_p90"])),
    "c1 builder-literal reproduced OLD on list / era A / big": tuple(int(x) for x in (olst.blit_old.sum(), olst[olst.era == "A"].blit_old.sum(), R1[R1.big].blit_old.sum())),
    "c1 builder-literal reproduced NEW on list / era A / big": tuple(int(x) for x in (olst.blit_new.sum(), olst[olst.era == "A"].blit_new.sum(), R1[R1.big].blit_new.sum())),
    "c2 ALL OLD med/mean": (RES["ALL"]["old_med"], round(RES["ALL"]["old_mean"], 1)),
    "c2 ALL on list / fire NEW / fire OLD": (RES["ALL"]["q_on"], RES["ALL"]["q_new"], RES["ALL"]["q_old"]),
    "c2 ALL big on / NEW / OLD": (RES["ALL"]["big_on"], RES["ALL"]["big_new"], RES["ALL"]["big_old"]),
    "c2 ALL top10/20/50": (RES["ALL"]["top10"], RES["ALL"]["top20"], RES["ALL"]["top50"]),
    "c2 A list med/mean": (RES["A"]["list_med"], round(RES["A"]["list_mean"])), "c2 A NEW med/mean": (RES["A"]["new_med"], round(RES["A"]["new_mean"], 1)),
    "c2 A on list / fire NEW / big NEW": (RES["A"]["q_on"], RES["A"]["q_new"], RES["A"]["big_new"]),
}
CL = {
    "c1 store minutes_rev_1024 holds": 0, "c1 covered pre_v2": 251, "c1 covered cb702": 18, "c1 mismatch excluded": 0,
    "c1 OLD on list": 143, "c1 NEW on list": 154, "c1 px on list": 193, "c1 OLD era A": 131, "c1 NEW era A": 141,
    "c1 OLD era B": 12, "c1 NEW era B": 13, "c1 OLD big": 15, "c1 NEW big": 17, "c1 px big": 23,
    "c1 literal(no-lapse-cancel, #500 kept) OLD on list": 160, "c1 literal(no-lapse-cancel, #500 kept) NEW on list": 172,
    "c1 literal(no-lapse-cancel, #500 kept) OLD big": 21, "c1 literal(no-lapse-cancel, #500 kept) NEW big": 20,
    "c1 builder-literal reproduced OLD on list / era A / big": (160, 147, 21),
    "c1 builder-literal reproduced NEW on list / era A / big": (172, 158, 20),
    "c2 B list median": 310, "c2 B list mean": 320, "c2 B list p90": 509, "c2 B NEW median": 26, "c2 B NEW mean": 36.3,
    "c2 B NEW p90": 78, "c2 B NEW days>5": 644, "c2 B OLD median": 23, "c2 B OLD mean": 30.1, "c2 B on list": 18,
    "c2 B fire NEW": 11, "c2 B fire OLD": 8, "c2 B top10/20/30/50": (2, 3, 3, 6),
    "c2 ALL list med/mean/p90": (249, 330, 609), "c2 ALL NEW med/mean/p90": (25, 37.5, 82), "c2 ALL OLD med/mean": (21, 30.8),
    "c2 ALL on list / fire NEW / fire OLD": (263, 156, 124), "c2 ALL big on / NEW / OLD": (26, 21, 15),
    "c2 ALL top10/20/50": (32, 51, 94), "c2 A list med/mean": (221, 336), "c2 A NEW med/mean": (24, 38.1),
    "c2 A on list / fire NEW / big NEW": (245, 145, 21),
}
say("\nCLAIMS vs MINE (stage0/s0.txt numbers; DIFF = a number that differs):")
ndiff = 0
for k in CL:
    a, b = CL[k], M[k]
    same = (tuple(float(x) for x in a) == tuple(float(x) for x in b)) if isinstance(a, tuple) else float(a) == float(b)
    ndiff += not same
    say(f"  {'MATCH' if same else 'DIFF '} {k:52s} claimed {a} | mine {b}")
say(f"  {ndiff} DIFF(s); the literal rows differ by DEFINITION (s0_check1.py's literal = buy at the first tick whose evaluate is ok + F1 "
    f"permits and bar m's high >= level: a lapse may re-permit AND the #500 width / chase cap is not applied; mine = the live path with only "
    f"the F1-lapse cancel removed)")
flush_log()

# ═════════════════════════════════════════════════════════════════════════════════════════════════
# 7. Look-ahead audit (what each decision reads)
# ═════════════════════════════════════════════════════════════════════════════════════════════════
say("\nLOOK-AHEAD AUDIT (by construction in this script):")
say("  list rules + order score: the feature table (bars <= D, built by 10_feature_table.py with breakout_v1.v1_gates) + rolling windows ending at D")
say("  daily buy test: high(E) and volume(E) = the E bar itself (the trigger event); level/averages end at D")
say("  intraday: tick m reads bars <= m-1 (evaluate), a resting order fills on bar m; the stop at the fill reads bars <= fill minute")
say("  data filters that read E's full day (not decisions): the 1% minute-vs-daily high/low check; the RTH-volume share statistic")
say("  big-winner label: realized_r >= 5 (membership only, as 11_starting_point.py)")
flush_log()
say("done")
flush_log()
