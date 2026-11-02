#!/usr/bin/env python3
"""Breakout v1 paper replay — the two follow-up tests on the FROZEN outcomes (PREREG.md in this folder, 2026-11-01).

No re-walk: every name-day's outcome is read from ../out/trades.tsv.gz. A slot order re-orders the names inside a
placement tick (a synthetic `list_rank`); a stop floor removes placed rows before the book. The book is
`v1_replay.apply_book`, IMPORTED and untouched. Stages (PREREG §9): tick | select | judge.

Offline, $0, nothing live changes, nothing dated 2025-01-01 or later is read (every frozen row has E <= 2024-12-31).
"""
from __future__ import annotations

import argparse
import gzip
import json
import math
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
PROBE = HERE.parent
sys.path.insert(0, str(PROBE))
import v1_replay as V  # noqa: E402  (the frozen replay module: apply_book, stats, verdict, the minute readers)
from agents.market_intelligence.broker import breakout_v1_entry as bve  # noqa: E402

TRADES = PROBE / "out" / "trades.tsv.gz"
TICK = HERE / "tick_facts.tsv.gz"
SEL = HERE / "selection_2017_21.txt"
CHOSEN = HERE / "chosen.json"
JUDGE = HERE / "judge_2022_24.txt"
ERA_A, ERA_B = "2017-21", "2022-24"
ORDERS = ("T", "R", "L", "P", "W")
FLOORS = ("0", "c5", "c10", "c15", "c20", "p0.5", "p1.0", "p1.5")
ORDER_WORDS = {"T": "today's: strongest first (list rank)", "R": "rs_best ascending (weakest RS first)",
               "L": "list rank 11+ before 1-10", "P": "volume pace at placement, highest first",
               "W": "tightest stop (share of price) first", "X": "random order (20 seeds) - the noise floor"}
FLOOR_WORDS = {"0": "no floor (today)", "c5": "stop under 5c skipped", "c10": "stop under 10c skipped",
               "c15": "stop under 15c skipped", "c20": "stop under 20c skipped", "p0.5": "stop under 0.5% of price skipped",
               "p1.0": "stop under 1.0% of price skipped", "p1.5": "stop under 1.5% of price skipped"}
N_SEEDS = 20
TIE = 0.005


# ───────────────────────────────────────────────── loading ─────────────────────────────────────────────────
def _none(x):
    if x is None:
        return None
    if isinstance(x, float) and math.isnan(x):
        return None
    return x


def _bool(x) -> bool:
    return str(x) == "True"


def load_placed() -> list:
    """Every placed row of the frozen file as the dict `apply_book` reads (NaN -> None, ints as ints)."""
    df = pd.read_csv(TRADES, sep="\t", low_memory=False)
    df = df[df.placed_m.notna()].copy()
    rows = []
    for r in df.to_dict("records"):
        legs = json.loads(r["legs"]) if isinstance(r["legs"], str) else []
        rows.append({
            "key": r["key"], "E": r["E"], "D": r["D"], "ticker": r["ticker"], "list_rank": int(r["list_rank"]),
            "rank_today": int(r["list_rank"]), "placed_m": int(r["placed_m"]),
            "cancel_m": (None if _none(r["cancel_m"]) is None else int(r["cancel_m"])),
            "filled": _bool(r["filled"]), "free_date": _none(r["free_date"]),
            "free_minute": (None if _none(r["free_minute"]) is None else int(r["free_minute"])),
            "exit_at_open": _bool(r["exit_at_open"]), "legs": legs,
            "f_risk": float(r["f_risk"]) if _none(r["f_risk"]) is not None else 0.0,
            "total_r": float(r["total_r"]) if _none(r["total_r"]) is not None else 0.0,
            "r_2c": float(r["r_2c"]) if _none(r["r_2c"]) is not None else None,
            "decisive": _bool(r["decisive"]), "era": r["era"], "month": r["month"], "year": int(r["year"]),
            "adm_cap": _none(r["adm_cap"]), "why_cap": _none(r["why_cap"]),
            "level": float(r["level"]), "orh5": float(r["orh5"]) if _none(r["orh5"]) is not None else None,
            "list_level": float(r["list_level"]), "adr20": _none(r["adr20"]), "vol_bar": float(r["vol_bar"]),
            "rs_best": float(r["rs_best"]), "raw_factor": float(r["raw_factor"]),
            "fill": _none(r["fill"]), "stop": _none(r["stop"]), "placed_stop": _none(r["placed_stop"]),
            "reprices": int(r["reprices"]), "stop_check": _none(r["stop_check"]),
        })
    for t in rows:
        if t["filled"]:
            assert t["free_date"] is not None, t["key"]
    return rows


# ───────────────────────────────────────────────── the tick facts (once) ─────────────────────────────────────────────────
def run_tick(rows: list) -> None:
    if TICK.exists():
        raise SystemExit(f"REFUSED — {TICK} exists (captured once, read many)")
    index = V.minute_index()
    by_e = defaultdict(list)
    for t in rows:
        by_e[t["E"]].append(t)
    out, bad = [], Counter()
    t0 = time.time()
    for n_e, e in enumerate(sorted(by_e)):
        names = by_e[e]
        src: dict = {}
        for t in names:
            src.setdefault(V.held_in(index, e, t["ticker"]), []).append(t["ticker"])
        blocks = {}
        for d, want in src.items():
            if d is None:
                continue
            files = next(f for dd, _, f in index if dd == d)
            done = next(dn for dd, dn, _ in index if dd == d)
            b, _info = V.runner.read_minute_file(files[e], set(want))
            for tk in want:
                blocks[tk] = V.runner.minutes_for(b, done, e, tk)
        for t in names:
            mb, state = blocks.get(t["ticker"], (None, "pending"))
            if state != "ok" or mb is None:
                bad["no_minutes"] += 1
                continue
            mins_all = V.minutes_to_dict(mb)
            m = t["placed_m"]
            mins = {k: v for k, v in mins_all.items() if k <= m - 1}
            st = bve.evaluate(mins, list_level=float(t["list_level"]), adr20=t["adr20"], vol_bar=float(t["vol_bar"]),
                              last_completed=m - 1)
            if st["status"] != "ok" or not st["f1_ok"]:
                bad["tick_not_ok"] += 1
            level, stop = float(st["level"]), float(st["stop"])
            if abs(level - t["level"]) > 1e-9 or (t["orh5"] is not None and abs(float(st["orh5"]) - t["orh5"]) > 1e-9):
                bad["level_mismatch"] += 1
            if t["filled"] and t["reprices"] == 0 and t["placed_stop"] is not None and abs(stop - float(t["placed_stop"])) > 1e-9:
                bad["stop_mismatch"] += 1
            out.append({"key": t["key"], "placed_m": m, "level_tick": level, "stop_tick": stop, "orh5_tick": float(st["orh5"]),
                        "cum_volume": float(st["cum_volume"]), "need_volume": float(st["need_volume"]),
                        "pace": float(st["cum_volume"]) / float(st["need_volume"]) if st["need_volume"] else float("nan"),
                        "width_pct": (level - stop) / level, "width_raw_cents": (level - stop) * t["raw_factor"] * 100.0})
        if n_e % 100 == 0:
            print(f"  day {n_e}/{len(by_e)} {e}: {len(out)} rows, {dict(bad)} ({time.time() - t0:.0f}s)", flush=True)
    pd.DataFrame(out).to_csv(TICK, sep="\t", index=False, compression="gzip")
    summary = {"rows": len(out), "placed": len(rows), "problems": dict(bad), "seconds": round(time.time() - t0)}
    (HERE / "tick_facts_summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary, indent=1))
    if bad["level_mismatch"] or bad["stop_mismatch"] or bad["no_minutes"]:
        raise SystemExit("the tick facts do not reproduce the frozen placement — see the summary")


def load_tick() -> dict:
    df = pd.read_csv(TICK, sep="\t")
    return {r["key"]: r for r in df.to_dict("records")}


# ───────────────────────────────────────────────── the levers ─────────────────────────────────────────────────
def with_order(rows: list, order: str, tick: dict, seed: int | None = None) -> list:
    """A copy of the rows with the synthetic `list_rank` of one candidate order (unique within each day; the sort
    inside a tick is the candidate's key, ties by today's rank)."""
    by_e = defaultdict(list)
    for t in rows:
        by_e[t["E"]].append(t)
    out = []
    for e in sorted(by_e):
        names = by_e[e]
        if order == "T":
            keyed = [((t["rank_today"],), t) for t in names]
        elif order == "R":
            keyed = [((t["rs_best"], t["rank_today"]), t) for t in names]
        elif order == "L":
            keyed = [((0 if t["rank_today"] >= 11 else 1, t["rank_today"]), t) for t in names]
        elif order == "P":
            keyed = [((-tick[t["key"]]["pace"], t["rank_today"]), t) for t in names]
        elif order == "W":
            keyed = [((tick[t["key"]]["width_pct"], t["rank_today"]), t) for t in names]
        elif order == "X":
            rng = np.random.default_rng([int(seed), int(e.replace("-", ""))])
            perm = rng.permutation(len(names))
            keyed = [((int(perm[i]),), t) for i, t in enumerate(names)]
        else:
            raise ValueError(order)
        # ONE order per DAY in the candidate's key (not per tick): `apply_book` sorts placements by (placed_m, rank) AND
        # uses the rank as the same-minute cancel tie-break ("the tick processes names in list order"), so the rank must
        # stay comparable across minutes — the live job iterates the list in this order at every tick. (A first draft
        # ranked per tick and broke the tie-break: today's order then admitted 1,051 instead of the frozen 1,058.)
        keyed.sort(key=lambda kt: tuple(kt[0]))
        for i, (_k, t) in enumerate(keyed):
            c = dict(t)
            c["list_rank"] = i + 1
            out.append(c)
    return out


def with_floor(rows: list, floor: str, tick: dict) -> list:
    """The rows whose planned risk at placement clears the floor (the others were never placed)."""
    if floor == "0":
        return list(rows)
    if floor.startswith("c"):
        x = float(floor[1:])
        return [t for t in rows if tick[t["key"]]["width_raw_cents"] >= x]
    if floor.startswith("p"):
        x = float(floor[1:]) / 100.0
        return [t for t in rows if tick[t["key"]]["width_pct"] >= x]
    raise ValueError(floor)


def book(rows: list, sessions: list) -> dict:
    return V.apply_book(rows, slots=V.CAP_SLOTS, safeguards=False, sessions=sessions)


def scored(rows: list, adm: dict, era: str) -> list:
    return [t for t in rows if adm["admitted"].get(t["key"]) and t["filled"] and t["decisive"] and t["era"] == era]


def line(name: str, pop: list, key: str, with_verdict: bool = False) -> tuple:
    s = V.stats(np.array([t["r_2c"] for t in pop]), [t["month"] for t in pop], key=key)
    txt = V.fmt_stats(name, s)
    if with_verdict:
        v, why = V.verdict(s)
        txt += f"   VERDICT {v} ({why})"
    return txt, s


# ───────────────────────────────────────────────── parity ─────────────────────────────────────────────────
def parity(rows: list, sessions: list) -> list:
    adm = book(rows, sessions)
    diff = [t["key"] for t in rows if str(adm["admitted"].get(t["key"])) != str(t["adm_cap"])]
    L = [f"parity: placed rows {len(rows):,}; admitted differs from the frozen adm_cap on {len(diff)} rows; "
         f"blocked {dict(adm['blocked'])} (frozen: max_positions 11,808 / ticker_open_position 1,260)"]
    for era, want in ((ERA_A, (1058, -0.153)), (ERA_B, (581, -0.412))):
        pop = scored(rows, adm, era)
        mean = float(np.mean([t["r_2c"] for t in pop]))
        L.append(f"parity {era}: n {len(pop)} mean {mean:+.3f} (frozen n {want[0]} mean {want[1]:+.3f})")
        if len(pop) != want[0] or abs(mean - want[1]) > 0.0015:
            diff.append(f"era {era} mismatch")
    if diff or dict(adm["blocked"]) != {"block:max_positions": 11808, "block:ticker_open_position": 1260}:
        raise SystemExit("PARITY FAILED:\n" + "\n".join(L) + "\n" + "\n".join(diff[:20]))
    return L


# ───────────────────────────────────────────────── select (2017-21 only) ─────────────────────────────────────────────────
def pick(cands: dict) -> str:
    """cands: id -> stats. The highest mean R; a tie within TIE -> the higher >= 3R share; still tied -> the first listed
    (today's is listed first in both tests)."""
    ids = list(cands)
    best = ids[0]
    for c in ids[1:]:
        a, b = cands[c], cands[best]
        if a["mean_r"] > b["mean_r"] + TIE:
            best = c
        elif abs(a["mean_r"] - b["mean_r"]) <= TIE and a["share_ge3"] > b["share_ge3"]:
            best = c
    return best


def run_select(rows: list, tick: dict) -> None:
    if CHOSEN.exists():
        raise SystemExit(f"REFUSED — {CHOSEN} exists: the selection runs once")
    sessions = sorted({t["E"] for t in rows})
    L = parity(rows, sessions)
    L.append("")
    L.append(f"SELECTION on {ERA_A} ONLY — capped book (guard + 5 slots) at 2c, admitted + filled + decisive rows (PREREG §6)")
    L.append("")
    L.append("TEST 1 — SLOT ORDER (within a placement tick; today's book otherwise)")
    o_stats = {}
    for o in ORDERS:
        adm = book(with_order(rows, o, tick), sessions)
        if o == "T":   # the lever's own check: today's order through the synthetic rank must be the frozen book exactly
            bad = [t["key"] for t in rows if str(adm["admitted"].get(t["key"])) != str(t["adm_cap"])]
            if bad:
                raise SystemExit(f"the synthetic rank for T differs from the frozen adm_cap on {len(bad)} rows: {bad[:5]}")
            L.append("lever check: today's order through the synthetic rank = the frozen adm_cap on every placed row")
        txt, s = line(f"{o}: {ORDER_WORDS[o]}"[:34], scored(rows, adm, ERA_A), key=f"bv1_followup|order|{o}|{ERA_A}")
        o_stats[o] = s
        L.append(txt + f"   admitted fills all years {sum(1 for t in rows if adm['admitted'].get(t['key']) and t['filled']):,}")
    rnd = []
    for seed in range(N_SEEDS):
        adm = book(with_order(rows, "X", tick, seed=seed), sessions)
        pop = scored(rows, adm, ERA_A)
        r = np.array([t["r_2c"] for t in pop])
        rnd.append({"seed": seed, "n": len(pop), "mean_r": float(r.mean()), "share_ge3": float((r >= 3).mean())})
    means = np.array([x["mean_r"] for x in rnd])
    L.append(f"X: random order, {N_SEEDS} seeds — mean R min {means.min():+.3f} / median {np.median(means):+.3f} / max {means.max():+.3f} "
             f"(sd {means.std(ddof=1):.3f}); n {min(x['n'] for x in rnd)}..{max(x['n'] for x in rnd)}; "
             f">=3R share {min(x['share_ge3'] for x in rnd):.1%}..{max(x['share_ge3'] for x in rnd):.1%}")
    chosen_o = pick(o_stats)
    inside = bool(means.min() <= o_stats[chosen_o]["mean_r"] <= means.max())
    L.append(f"-> chosen slot order on {ERA_A}: {chosen_o} ({ORDER_WORDS[chosen_o]}), mean {o_stats[chosen_o]['mean_r']:+.3f}; "
             f"today's T {o_stats['T']['mean_r']:+.3f}; {'INSIDE' if inside else 'outside'} the random range "
             f"[{means.min():+.3f}, {means.max():+.3f}]" + (" -> not separable from a random order; today's order is kept" if inside else ""))
    L.append("")
    L.append("TEST 2 — MINIMUM STOP (planned risk at placement = level - day-low stop; rows under the floor removed before the book; today's order)")
    f_stats, f_rows = {}, {}
    for f in FLOORS:
        kept = with_floor(rows, f, tick)
        adm = book(with_order(kept, "T", tick), sessions)
        txt, s = line(f"{f}: {FLOOR_WORDS[f]}"[:34], scored(kept, adm, ERA_A), key=f"bv1_followup|floor|{f}|{ERA_A}")
        f_stats[f] = s
        removed = len(rows) - len(kept)
        L.append(txt + f"   placed rows removed {removed:,} of {len(rows):,}")
    chosen_f = pick(f_stats)
    L.append(f"-> chosen stop floor on {ERA_A}: {chosen_f} ({FLOOR_WORDS[chosen_f]}), mean {f_stats[chosen_f]['mean_r']:+.3f}; "
             f"today's (no floor) {f_stats['0']['mean_r']:+.3f}")
    # beside: the literal fill - stop reading vs the planned reading, on today's admitted decisive filled rows
    adm0 = book(rows, sessions)
    base = [t for t in rows if adm0["admitted"].get(t["key"]) and t["filled"] and t["decisive"]]
    L.append("")
    L.append("beside — on today's 1,639 admitted decisive trades: rows the literal (fill - stop) reading and the planned (level - stop at placement) reading classify differently")
    for f in FLOORS[1:]:
        if f.startswith("c"):
            x = float(f[1:])
            lit = {t["key"] for t in base if (t["fill"] - t["stop"]) * t["raw_factor"] * 100.0 < x}
        else:
            x = float(f[1:]) / 100.0
            lit = {t["key"] for t in base if (t["fill"] - t["stop"]) / t["fill"] < x}
        pln = {t["key"] for t in base if t["key"] not in {k["key"] for k in with_floor(base, f, tick)}}
        L.append(f"  {f:5s} literal under the floor {len(lit):4d}; planned under the floor {len(pln):4d}; differ on {len(lit ^ pln):3d}")
    SEL.write_text("\n".join(L) + "\n")
    CHOSEN.write_text(json.dumps({"order": chosen_o, "order_inside_random_range": inside, "floor": chosen_f,
                                  "random_range_2017_21": [float(means.min()), float(means.max())],
                                  "era_a_means": {o: o_stats[o]["mean_r"] for o in ORDERS},
                                  "era_a_floor_means": {f: f_stats[f]["mean_r"] for f in FLOORS}}, indent=1))
    print("\n".join(L))


# ───────────────────────────────────────────────── judge (2022-24) ─────────────────────────────────────────────────
def run_judge(rows: list, tick: dict) -> None:
    if JUDGE.exists():
        raise SystemExit(f"REFUSED — {JUDGE} exists: the judging runs once")
    ch = json.loads(CHOSEN.read_text())
    o, f = ch["order"], ch["floor"]
    sessions = sorted({t["E"] for t in rows})
    L = [f"JUDGING on {ERA_B} — capped book at 2c, admitted + filled + decisive rows; the bar of the replay registration §6 "
         f"(PASS: n>=100, lower end > 0, >=3R share >= 8%; FAIL: n>=100, upper end < +0.25R, share < 8%; else CAN'T TELL)",
         f"chosen on {ERA_A}: slot order {o} ({ORDER_WORDS[o]}){' - INSIDE the random range, today kept' if ch['order_inside_random_range'] else ''}; "
         f"stop floor {f} ({FLOOR_WORDS[f]})", ""]
    rows_of = {
        "today (T, no floor)": with_order(rows, "T", tick),
        f"chosen order {o}": with_order(rows, o, tick),
        f"chosen floor {f}": with_order(with_floor(rows, f, tick), "T", tick),
        f"combined {o} + {f}": with_order(with_floor(rows, f, tick), o, tick),
    }
    res = {}
    for era in (ERA_B, ERA_A):
        L.append(f"-- era {era} --" + ("  (the selection era: in-sample, context only)" if era == ERA_A else "  (THE JUDGED ERA)"))
        for name, rr in rows_of.items():
            adm = book(rr, sessions)
            txt, s = line(name[:34], scored(rr, adm, era), key=f"bv1_followup|judge|{name}|{era}", with_verdict=(era == ERA_B))
            res[(name, era)] = s
            L.append(txt)
        rnd = []
        for seed in range(N_SEEDS):
            adm = book(with_order(rows, "X", tick, seed=seed), sessions)
            r = np.array([t["r_2c"] for t in scored(rows, adm, era)])
            rnd.append(float(r.mean()))
        rnd = np.array(rnd)
        res[("random", era)] = {"min": float(rnd.min()), "max": float(rnd.max()), "median": float(np.median(rnd))}
        L.append(f"{'random order, 20 seeds (reference)':34s} mean R min {rnd.min():+.3f} / median {np.median(rnd):+.3f} / max {rnd.max():+.3f} "
                 f"(range width {rnd.max() - rnd.min():.3f})")
        L.append("")
    width = res[("random", ERA_B)]["max"] - res[("random", ERA_B)]["min"]
    today_b, today_a = res[("today (T, no floor)", ERA_B)]["mean_r"], res[("today (T, no floor)", ERA_A)]["mean_r"]
    L.append("PRE-DECLARED READS (PREREG §7): 'beats today's' = the 2022-24 mean above today's by more than the random range width AND above today's on 2017-21 too")
    for name in list(rows_of)[1:]:
        b, a = res[(name, ERA_B)]["mean_r"], res[(name, ERA_A)]["mean_r"]
        beats = (b - today_b) > width and (a - today_a) > 0
        v, _ = V.verdict(res[(name, ERA_B)])
        L.append(f"  {name:28s} {ERA_B} {b:+.3f} vs today {today_b:+.3f} (diff {b - today_b:+.3f}; random width {width:.3f}); "
                 f"{ERA_A} diff {a - today_a:+.3f} -> {'BEATS today' if beats else 'does NOT beat today beyond noise'}; verdict {v}")
    JUDGE.write_text("\n".join(L) + "\n")
    (HERE / "judge_2022_24.json").write_text(json.dumps({f"{k[0]}|{k[1]}": v for k, v in res.items()}, indent=1, default=float))
    print("\n".join(L))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["tick", "select", "judge"])
    a = ap.parse_args(argv)
    rows = load_placed()
    if a.stage == "tick":
        run_tick(rows)
    elif a.stage == "select":
        run_select(rows, load_tick())
    else:
        run_judge(rows, load_tick())
    return 0


if __name__ == "__main__":
    sys.exit(main())
