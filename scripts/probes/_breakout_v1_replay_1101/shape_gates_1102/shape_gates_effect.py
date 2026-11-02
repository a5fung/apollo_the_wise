"""The three shape gates (DEFINITIONS.md, fixed before this ran) on the frozen paper-baseline replay. Read-only.

Pattern = adr_floor_1102/adr_floor_effect.py: a tighter gate only REMOVES list rows, so the existing walked outcomes
(out/trades.tsv.gz) are re-booked on the subset (5 slots, 2c) — no new data. Every candidate sits ON TOP of the
4.26% daily-range floor (live since 11-02); the baseline row is the floor-only book.

Stage 1 (`gates`): each list row's three gates at its watch night D from the sealed daily stores, bars <= D only ->
gates_rows.tsv.gz (+ parity: the pole date and the level recomputed here must equal the frozen list row's).
Stage 2 (`book`): the tables -> shape_gates_effect.txt."""
import gzip
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
PROBE = HERE.parent
REPO = HERE.parents[3]
for p in (REPO, PROBE, PROBE / "followup_tests_1101", HERE):
    sys.path.insert(0, str(p))
from agents.market_intelligence import breakout_v1 as bv            # noqa: E402
from agents.market_intelligence import consolidation_breakout as cb  # noqa: E402
from scripts.probes._cb_backtest import runner                       # noqa: E402
import gates_patch as G                                               # noqa: E402

SEAL = date(2025, 1, 1)
STORES = {"A": Path("/Users/alvinfung/apollo_data/cb702_pre_v2/daily_closes_all.csv.gz"),
          "B": Path("/private/tmp/claude-501/-Users-alvinfung-apollo-the-wise/d30e3944-e07e-4b44-97de-010acba78d0b/"
                    "scratchpad/Creplay/pop/cb702_daily_lt2025.csv.gz")}   # the replay's own sealed (< 2025) copy
ROWS = HERE / "gates_rows.tsv.gz"
NEW = ("riding", "rising_lows", "no_failed_attempt")
FLOOR = bv.ADR_MIN


def stage_gates():
    meta = json.loads(Path(str(STORES["B"]) + ".src.json").read_text())
    assert meta["seal"] == SEAL.isoformat(), meta
    out, parity = [], Counter()
    for era in ("A", "B"):
        lst = pd.read_csv(PROBE / "out" / f"list_era{era}.tsv.gz", sep="\t", keep_default_na=False)
        Dd = runner.load_daily(STORES[era])
        assert Dd.cal[-1] < SEAL, Dd.cal[-1]
        for t, grp in lst.groupby("ticker"):
            bars, _ = runner.bars_for(Dd, Dd.tid[t])
            pos = {d: i for i, d in enumerate(bars.dates)}
            with np.errstate(invalid="ignore", divide="ignore"):
                rng = (bars.h - bars.l) / bars.c
            for r in grp.itertuples(index=False):
                D = pos[date.fromisoformat(r.scan_date)]
                # bars <= D only: every function below reads indices <= D (asserted on a truncated copy for a sample)
                P = cb._pole_top(bars.h, bars.c, D - bv.BASE_MAX, D - bv.BASE_MIN)
                level = float(bars.h[D - 4:D + 1].max())
                parity["pole_ok" if str(bars.dates[P]) == r.pole_date else "pole_MISMATCH"] += 1
                parity["level_ok" if abs(level - float(r.level)) < 1e-9 else "level_MISMATCH"] += 1
                g1 = G.riding_gate(bars, rng, D)
                g2 = G.rising_lows_gate(bars, D)
                g3 = G.no_failed_attempt_gate(bars, D, P)
                if len(out) % 997 == 0:          # look-ahead check: the same gates on bars cut at D
                    cut = cb.daily_bars_from_arrays(bars.dates[:D + 1], bars.o[:D + 1], bars.h[:D + 1], bars.l[:D + 1],
                                                    bars.c[:D + 1], bars.v[:D + 1])
                    same = (G.riding_gate(cut, rng[:D + 1], D)["pass"] == g1["pass"]
                            and G.rising_lows_gate(cut, D)["pass"] == g2["pass"]
                            and G.no_failed_attempt_gate(cut, D, P)["pass"] == g3["pass"])
                    parity["cut_ok" if same else "cut_MISMATCH"] += 1
                out.append({"key": f"{r.E}|{t}", "era_store": era, "scan_date": r.scan_date, "ticker": t,
                            "riding": int(g1["pass"]), "rising_lows": int(g2["pass"]), "no_failed_attempt": int(g3["pass"]),
                            "ride10": int(g1["value"]["sma10"]["pass"]), "ride20": int(g1["value"]["sma20"]["pass"]),
                            "attempted": int(bool(g3["value"].get("attempted")))})
        del Dd
        print(f"era {era}: {len(lst)} list rows done; parity so far {dict(parity)}", flush=True)
    df = pd.DataFrame(out)
    df.to_csv(ROWS, sep="\t", index=False, compression="gzip")
    (HERE / "gates_parity.json").write_text(json.dumps(dict(parity), indent=1))
    print(dict(parity))
    assert not any("MISMATCH" in k for k in parity), parity


def stage_book():
    import v1_replay as V
    import followup as F
    lines = []

    def say(s=""):
        print(s, flush=True)
        lines.append(s)

    g = pd.read_csv(ROWS, sep="\t").set_index("key")
    rows = F.load_placed()
    sessions = sorted({t["E"] for t in rows})
    missing = [t["key"] for t in rows if t["key"] not in g.index]
    assert not missing, missing[:5]
    for t in rows:
        rec = g.loc[t["key"]]
        for k in NEW:
            t[k] = bool(rec[k])
    floor = [t for t in rows if t["adr20"] is not None and float(t["adr20"]) >= FLOOR]
    say(f"placed name-days {len(rows)}; floor-kept (ADR20 >= 4.26%) {len(floor)} — every candidate below starts from these")
    say("list rows (all, before the floor) passing each gate: " + ", ".join(
        f"{k} {int(g[k].sum())}/{len(g)} ({g[k].mean():.0%})" for k in NEW)
        + f", all three {int(g[list(NEW)].all(axis=1).sum())}/{len(g)} ({g[list(NEW)].all(axis=1).mean():.0%})")

    def dec(ts):
        return [t for t in ts if t["filled"] and t["decisive"] and t["r_2c"] is not None]

    def st(ts):
        r = np.array([t["r_2c"] for t in ts])
        if not len(r):
            return {"n": 0}
        return {"n": len(r), "mean": float(r.mean()), "win": float(np.mean(r > 0)), "r3": float(np.mean(r >= 3)),
                "r10": int(np.sum(r >= 10)), "sum": float(r.sum())}

    def fs(s):
        if not s["n"]:
            return "n     0"
        return (f"n {s['n']:5d} mean {s['mean']:+.3f} win {s['win']:.1%} 3R+ {s['r3']:.1%} 10R+ {s['r10']:3d} "
                f"sum {s['sum']:+.0f}")

    cands = {"floor only (BASELINE)": lambda t: True,
             "G1 riding": lambda t: t["riding"],
             "G2 rising lows": lambda t: t["rising_lows"],
             "G3 no failed attempt": lambda t: t["no_failed_attempt"],
             "all three": lambda t: t["riding"] and t["rising_lows"] and t["no_failed_attempt"]}
    res = {}
    for name, fn in cands.items():
        kept = [t for t in floor if fn(t)]
        removed = [t for t in floor if not fn(t)]
        book = V.apply_book([dict(t) for t in kept], slots=V.CAP_SLOTS, safeguards=False, sessions=sessions)
        adm = [t for t in kept if book["admitted"].get(t["key"])]
        gbook = V.apply_book([dict(t) for t in kept], slots=None, safeguards=False, sessions=sessions)
        gadm = [t for t in kept if gbook["admitted"].get(t["key"])]
        r = {"orders_kept": len(kept), "orders_removed": len(removed)}
        for era in ("2017-21", "2022-24", None):
            sel = (lambda t: True) if era is None else (lambda t, e=era: t["era"] == e)
            r[("book", era)] = st(dec([t for t in adm if sel(t)]))
            r[("guard", era)] = st(dec([t for t in gadm if sel(t)]))
            r[("kept", era)] = st(dec([t for t in kept if sel(t)]))
            r[("removed", era)] = st(dec([t for t in removed if sel(t)]))
        res[name] = r
    say()
    say("=== 5-slot paper book, 2c (the paper account) ===")
    for name, r in res.items():
        for era in ("2017-21", "2022-24", None):
            say(f"  {name:24s} {era or 'all':8s} {fs(r[('book', era)])}")
    say()
    say("=== same-ticker guard only, no slot limit, 2c (adr_floor_effect's 'no slot limit' rows) ===")
    for name, r in res.items():
        for era in ("2017-21", "2022-24", None):
            say(f"  {name:24s} {era or 'all':8s} {fs(r[('guard', era)])}")
    say()
    say("=== removed vs kept, no slot limit, 2c (filled + decisive trades, from the floor-kept set) ===")
    for name, r in res.items():
        if name.startswith("floor"):
            say(f"  {name:24s} kept    all      {fs(r[('kept', None)])}")
            continue
        say(f"  {name:24s} orders kept {r['orders_kept']}, removed {r['orders_removed']} "
            f"({r['orders_removed'] / (r['orders_kept'] + r['orders_removed']):.0%})")
        for era in ("2017-21", "2022-24", None):
            say(f"  {'':24s} kept    {era or 'all':8s} {fs(r[('kept', era)])}")
            say(f"  {'':24s} removed {era or 'all':8s} {fs(r[('removed', era)])}")
    # the reproduction of the baseline (adr_floor_effect.txt): 5 slots 2017-21 n 983 -0.139, 2022-24 n 556 -0.340
    b = res["floor only (BASELINE)"]
    rep = (b[("book", "2017-21")]["n"] == 983 and round(b[("book", "2017-21")]["mean"], 3) == -0.139
           and b[("book", "2022-24")]["n"] == 556 and round(b[("book", "2022-24")]["mean"], 3) == -0.340
           and b[("guard", None)]["n"] == 4029 and round(b[("guard", None)]["mean"], 3) == -0.092)
    lo = st(dec([t for t in rows if t["adr20"] is not None and float(t["adr20"]) < FLOOR]))
    rep = rep and lo["n"] == 919 and round(lo["mean"], 3) == -0.464
    say()
    say(f"baseline reproduction of adr_floor_effect.txt (5 slots 983 @ -0.139, 556 @ -0.340; guard-only 4029 @ -0.092; floor-removed raw 919 @ -0.464): {'PASS' if rep else 'FAIL'}")
    say()
    say("=== bar (c) per candidate ===")
    for name, r in res.items():
        if name.startswith("floor"):
            continue
        a, bb = r[("book", "2017-21")], r[("book", "2022-24")]
        c1 = a["n"] and bb["n"] and a["mean"] >= -0.139 and bb["mean"] >= -0.340
        c2 = r[("removed", None)]["n"] and r[("removed", None)]["mean"] < r[("kept", None)]["mean"]
        c3 = a["n"] >= 100 and bb["n"] >= 100
        say(f"  {name:24s} c1 book >= baseline both eras: {'PASS' if c1 else 'FAIL'} ({a.get('mean', 0):+.3f} / "
            f"{bb.get('mean', 0):+.3f}) | c2 removed below kept: {'PASS' if c2 else 'FAIL'} "
            f"({r[('removed', None)].get('mean', 0):+.3f} vs {r[('kept', None)].get('mean', 0):+.3f}) | "
            f"c3 n >= 100 per era: {'PASS' if c3 else 'FAIL'} ({a['n']} / {bb['n']})")
    say()
    say("=== POST-HOC DIAGNOSTIC (not part of the bar): the same share of orders removed AT RANDOM, 200 draws, 5-slot book ===")
    rng = np.random.default_rng(1102)
    for name, fn in list(cands.items())[1:]:
        share = res[name]["orders_kept"] / len(floor)
        draws = {"2017-21": [], "2022-24": []}
        for _ in range(200):
            keep = rng.random(len(floor)) < share
            kept = [t for t, k in zip(floor, keep) if k]
            bk = V.apply_book([dict(t) for t in kept], slots=V.CAP_SLOTS, safeguards=False, sessions=sessions)
            adm = [t for t in kept if bk["admitted"].get(t["key"])]
            for era in draws:
                draws[era].append(st(dec([t for t in adm if t["era"] == era]))["mean"])
        msg = []
        for era in draws:
            d = np.array(draws[era]); got = res[name][("book", era)]["mean"]
            msg.append(f"{era}: gate {got:+.3f} vs random median {np.median(d):+.3f} (5-95% {np.percentile(d, 5):+.3f}..{np.percentile(d, 95):+.3f}); "
                       f"random beats the gate in {np.mean(d >= got):.0%} of draws")
        say(f"  {name:24s} keep {share:.0%} | " + " | ".join(msg))
    (HERE / "shape_gates_effect.txt").write_text("\n".join(lines) + "\n")
    (HERE / "shape_gates_effect.json").write_text(json.dumps(
        {n: {str(k): v for k, v in r.items()} for n, r in res.items()}, indent=1))


if __name__ == "__main__":
    {"gates": stage_gates, "book": stage_book}[sys.argv[1]]()
