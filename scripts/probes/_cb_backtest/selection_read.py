#!/usr/bin/env python3
"""#702 selection test - THE READ (docs/analysis/cb_selection_test_prereg_2026-10-19.md). Written and unit-tested on SYNTHETIC data only.

NOT RUN on the real picks by the build card: the main loop runs it AFTER checking the population report
(`/Users/alvinfung/apollo_data/cb702_pre/out/selection_population.txt`). This is the only script of the selection test that reads a bar after
a breakout day; `selection_pre.py` (the build) never does.

  python scripts/probes/_cb_backtest/selection_read.py --data /Users/alvinfung/apollo_data/cb702_pre

Reads `out/selection_picks.tsv`, `out/selection_controls_a.tsv`, `out/selection_controls_b.tsv` (keys: ticker, level, E, E_ci, month, pivot,
adr20) and the daily bars of the same data dir. Writes `out/selection_result.txt` and `out/selection_result.tsv`.

THE METRICS (pre-registered; ADR unit = level x ADR20, with ADR20 as of E-1 = the candidate's `adr20`, and `level` = the candidate's `pivot`,
the breakout level projected to E from bars up to the night before):
  fwd20    (close of E+20 - level) / (level x ADR20)                     the DECISIVE metric: it measures the base, not the entry
  mfe10    (max high over sessions E..E+10 - level) / (level x ADR20)    max favourable excursion
  mfe20    (max high over sessions E..E+20 - level) / (level x ADR20)
  reach5   1 if mfe20 >= 5 else 0                                        share reaching +5 ADR within 20 sessions
  "E+k" = k sessions of the SPY calendar after E. The window INCLUDES E (an entry at the level fills during E, so E's high is favourable
  excursion after the fill - the registration does not say, so this is the choice made here and stated). A window that crosses a missing
  session, runs past the ticker's last bar (delisted / data end) or past the last session of the data is NOT scored: it is counted by
  reason (`hole` | `ended` | `immature`), never filled in.

THE BAR (pre-registered): difference = picks' mean - control (a)'s MONTH-MATCHED mean: each pick is compared with the mean of the controls whose
E is in the same calendar month, and the difference is the mean of those pick-minus-control values (a pick in a month with no scored control
is excluded and counted). 95% interval: month-block bootstrap, 2,000 resamples, seed 702 (the runner's `BOOT_DRAWS` / `BOOT_SEED`; each
comparison has its own fixed stream, seeded from the seed and a key). Every resample also redraws the controls inside their own group (month
for (a), ticker for (b)) before the month blocks of the picks are drawn, so the interval carries the controls' sampling noise too - the registration
says "month-block bootstrap" and is silent on it; with ~8 controls per ticker in (b) a bootstrap that held the control means fixed would be
visibly too narrow, so the wider reading is the one made here (`matched_diff(ctrl=None)` is the pick-side-only version, kept for the tests).
Lower end > 0 -> HIS SELECTION ADDS EDGE; upper end < 0 -> HIS PICKS DID
WORSE; otherwise CAN'T TELL; fewer than 30 scored picks is CAN'T TELL whatever the interval says. Control (b) (each pick against the mean of the
OTHER first breakouts of its own ticker) and the frame-verified subset are reported beside with the same interval and decide nothing. The
verdict is stated on `fwd20` only; the other metrics are read beside it.
"""
from __future__ import annotations

import argparse
import sys
import zlib
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[2]))

import runner  # noqa: E402  (load_daily, BOOT_DRAWS, BOOT_SEED)

PRE = Path("/Users/alvinfung/apollo_data/cb702_pre")
METRICS = ("fwd20", "mfe10", "mfe20", "reach5")
DECISIVE = "fwd20"
MIN_PICKS = 30
REACH_ADR = 5.0
LEVELS = ("tl", "com")                                 # tl = the registered level; com beside
NAN = float("nan")


# ═══ one breakout → its forward numbers ═══════════════════════════════════════════════════════════
def item_metrics(ci: np.ndarray, high: np.ndarray, close: np.ndarray, e_ci: int, level: float, adr20: float, cal_last_ci: int) -> dict:
    """The forward numbers of ONE breakout from its ticker's bars (`ci` = SPY-calendar index of every bar, ascending). Each horizon is scored
    on its own: `st10` / `st20` is 'ok' or why it was not (no_E_bar | bad_level | immature | ended | hole)."""
    out = {"fwd20": NAN, "mfe10": NAN, "mfe20": NAN, "reach5": NAN, "st10": "ok", "st20": "ok"}
    p = int(np.searchsorted(ci, e_ci))
    if p >= len(ci) or int(ci[p]) != e_ci:
        return {**out, "st10": "no_E_bar", "st20": "no_E_bar"}
    if not (np.isfinite(level) and np.isfinite(adr20) and level > 0 and adr20 > 0):
        return {**out, "st10": "bad_level", "st20": "bad_level"}
    unit = level * adr20
    for k in (10, 20):
        end = p + k
        if e_ci + k > cal_last_ci:
            out[f"st{k}"] = "immature"
        elif end >= len(ci):
            out[f"st{k}"] = "ended"
        elif int(ci[end]) - int(ci[p]) != k:
            out[f"st{k}"] = "hole"
        else:
            out[f"mfe{k}"] = (float(np.max(high[p:end + 1])) - level) / unit
            if k == 20:
                out["fwd20"] = (float(close[end]) - level) / unit
    if np.isfinite(out["mfe20"]):
        out["reach5"] = float(out["mfe20"] >= REACH_ADR)
    return out


def score_frame(df: pd.DataFrame, bars, cal_last_ci: int) -> pd.DataFrame:
    """`df` (columns ticker, E_ci, pivot, adr20) + the forward numbers. `bars(ticker)` -> (ci, high, close) or None (no series)."""
    rows = []
    for t, e_ci, lv, adr in zip(df["ticker"], df["E_ci"], df["pivot"], df["adr20"]):
        b = bars(t)
        if b is None:
            rows.append({"fwd20": NAN, "mfe10": NAN, "mfe20": NAN, "reach5": NAN, "st10": "no_series", "st20": "no_series"})
        else:
            rows.append(item_metrics(b[0], b[1], b[2], int(e_ci), float(lv), float(adr), cal_last_ci))
    return pd.concat([df.reset_index(drop=True), pd.DataFrame(rows)], axis=1)


# ═══ the difference and its month-block bootstrap ═══════════════════════════════════════════════
def group_means(values, groups) -> dict:
    """{group: mean of the finite values of that group}."""
    acc: dict = {}
    for v, g in zip(values, groups):
        if np.isfinite(v):
            s = acc.setdefault(g, [0.0, 0])
            s[0] += float(v)
            s[1] += 1
    return {g: s[0] / s[1] for g, s in acc.items()}


def matched_means(ctrl_values, ctrl_groups, pick_groups) -> np.ndarray:
    """For every pick, the mean of the scored controls in its own group (month for control (a), ticker for control (b)); NaN = none."""
    m = group_means(ctrl_values, ctrl_groups)
    return np.array([m.get(g, NAN) for g in pick_groups], dtype=float)


def matched_diff(x, blocks, m, *, key: str, draws: int = runner.BOOT_DRAWS, seed: int = runner.BOOT_SEED, ctrl=None) -> dict:
    """Mean of (pick - its matched control mean) over the picks that have both, with a month-block bootstrap 95% interval: whole month blocks
    (`blocks` = the month of each pick's E) are resampled with replacement, as many as there are months, `draws` times. A pick or control that
    was not scored (NaN) is excluded and counted in `n_excluded`.

    Control sampling noise. With `ctrl=None` the matched control means `m` are treated as KNOWN and only the pick side varies - fine for control
    (a) at ~460 controls a month, too narrow for control (b) at ~8 per ticker. With `ctrl=(control values, control groups, pick groups)` (what
    `compare_level` passes) EVERY draw also resamples the controls with replacement inside their own group (month for (a), ticker for (b)),
    recomputes each pick's matched mean from them, and only then resamples the month blocks of the picks: the interval carries both sources.
    The point estimate is the same either way."""
    x, m, blocks = np.asarray(x, dtype=float), np.asarray(m, dtype=float), np.asarray(blocks)
    ok = np.isfinite(x) & np.isfinite(m)
    res = {"n": int(ok.sum()), "n_excluded": int(len(x) - ok.sum()), "pick_mean": NAN, "ctrl_mean": NAN, "diff": NAN, "lo": NAN, "hi": NAN}
    if not ok.any():
        return res
    d = x[ok] - m[ok]
    uniq, inv = np.unique(blocks[ok], return_inverse=True)
    sums = np.bincount(inv, weights=d, minlength=len(uniq))
    cnts = np.bincount(inv, minlength=len(uniq)).astype(float)
    rng = np.random.default_rng([seed, zlib.crc32(key.encode())])
    if ctrl is None:
        idx = rng.integers(0, len(uniq), size=(draws, len(uniq)))
        boot = sums[idx].sum(axis=1) / cnts[idx].sum(axis=1)
    else:
        cv, cg, pg = np.asarray(ctrl[0], dtype=float), np.asarray(ctrl[1]), np.asarray(ctrl[2])
        keep = np.isfinite(cv)
        cv, cg = cv[keep], cg[keep]
        order = np.argsort(cg, kind="stable")
        cv, cg = cv[order], cg[order]
        ug, ginv, gcnt = np.unique(cg, return_inverse=True, return_counts=True)
        gstart = np.concatenate(([0], np.cumsum(gcnt)[:-1]))
        pick_g = np.searchsorted(ug, pg[ok])                                # every kept pick has a control group (it was matched)
        xo = x[ok]
        boot = np.empty(draws)
        for k in range(draws):
            r = gstart[ginv] + np.floor(rng.random(len(cv)) * gcnt[ginv]).astype(np.int64)      # a draw inside each control's own group
            gm = np.bincount(ginv, weights=cv[r], minlength=len(ug)) / gcnt
            bs = np.bincount(inv, weights=xo - gm[pick_g], minlength=len(uniq))
            sel = rng.integers(0, len(uniq), size=len(uniq))
            boot[k] = bs[sel].sum() / cnts[sel].sum()
    res.update(pick_mean=float(x[ok].mean()), ctrl_mean=float(m[ok].mean()), diff=float(d.mean()),
               lo=float(np.percentile(boot, 2.5)), hi=float(np.percentile(boot, 97.5)))
    return res


def verdict(n: int, lo: float, hi: float) -> str:
    """The pre-registered reading. n < 30 scored picks is CAN'T TELL whatever the interval says."""
    if n < MIN_PICKS or not (np.isfinite(lo) and np.isfinite(hi)):
        return "CAN'T TELL"
    if lo > 0:
        return "HIS SELECTION ADDS EDGE"
    if hi < 0:
        return "HIS PICKS DID WORSE"
    return "CAN'T TELL"


# ═══ one level → every comparison ═════════════════════════════════════════════════════════════════
def compare_level(picks: pd.DataFrame, ca: pd.DataFrame, cb: pd.DataFrame, level: str, bars, cal_last_ci: int) -> dict:
    """Score the three frames at `level` and run: picks vs control (a) [primary], vs control (b), frame-verified picks vs control (a)."""
    p = score_frame(picks, bars, cal_last_ci)
    a = score_frame(ca, bars, cal_last_ci)
    b = score_frame(cb, bars, cal_last_ci)
    rows = []
    fv = p["frame_verified"].astype(int) == 1
    for metric in METRICS:
        for comp, frame, mask in (("picks_vs_a", a, np.ones(len(p), bool)), ("picks_vs_b", b, np.ones(len(p), bool)),
                                  ("frame_vs_a", a, fv.to_numpy())):
            groups_c = frame["month"] if frame is a else frame["ticker"]
            groups_p = p["month"] if frame is a else p["ticker"]
            m = matched_means(frame[metric], groups_c, groups_p)
            d = matched_diff(p[metric][mask], p["month"][mask], m[mask], key=f"{level}|{metric}|{comp}",
                             ctrl=(frame[metric], groups_c, np.asarray(groups_p)[mask]))
            rows.append({"level": level, "metric": metric, "comparison": comp, **d,
                         "n_picks": int(mask.sum()), "n_ctrl_scored": int(np.isfinite(frame[metric]).sum()), "n_ctrl": len(frame),
                         "ctrl_median": float(np.nanmedian(frame[metric])) if np.isfinite(frame[metric]).any() else NAN,
                         "pick_median": float(np.nanmedian(p[metric][mask])) if np.isfinite(p[metric][mask]).any() else NAN,
                         "verdict": verdict(d["n"], d["lo"], d["hi"]) if metric == DECISIVE else ""})
    status = {name: dict(Counter(f["st20"])) for name, f in (("picks", p), ("control_a", a), ("control_b", b))}
    return {"rows": rows, "status": status, "n_picks": len(p)}


# ═══ report ═══════════════════════════════════════════════════════════════════════════════════════
def _f(x, nd=3) -> str:
    return "n/a" if x is None or not np.isfinite(x) else f"{x:+.{nd}f}"


def result_text(results: dict) -> str:
    L = []
    A = L.append
    A("#702 SELECTION TEST - THE READ (pre-registered: docs/analysis/cb_selection_test_prereg_2026-10-19.md)")
    A("difference = picks' mean - the month-matched mean of control (a); 95% interval = month-block bootstrap (2,000 resamples, seed 702), "
      "the controls redrawn inside their own month (b: ticker) in every resample.")
    for level, r in results.items():
        pri = next(x for x in r["rows"] if x["metric"] == DECISIVE and x["comparison"] == "picks_vs_a")
        A("")
        A(f"LEVEL {level}" + ("  (the registered level)" if level == LEVELS[0] else "  (beside)")
          + f" - VERDICT on the 20-session forward return in ADR units: {pri['verdict']}"
          + f"  [difference {_f(pri['diff'])}, interval {_f(pri['lo'])} .. {_f(pri['hi'])}, {pri['n']} scored picks]")
        A(f"  window not scored (E+20 not reachable), by reason: " + "; ".join(f"{k}: {dict(sorted(v.items()))}" for k, v in r["status"].items()))
        hdr = ["metric", "comparison", "n picks", "pick mean", "control mean", "difference", "95% lo", "95% hi", "excluded", "reading"]
        body = []
        for x in r["rows"]:
            body.append([x["metric"], x["comparison"] + ("" if x["comparison"] == "picks_vs_a" else "  (beside)"), x["n"], _f(x["pick_mean"]),
                         _f(x["ctrl_mean"]), _f(x["diff"]), _f(x["lo"]), _f(x["hi"]), x["n_excluded"],
                         (x["verdict"] if x["metric"] == DECISIVE and x["comparison"] == "picks_vs_a" else
                          verdict(x["n"], x["lo"], x["hi"]) + " (beside; decides nothing)" if x["metric"] == DECISIVE else "")])
        cells = [hdr] + [[str(c) for c in row] for row in body]
        w = [max(len(row[k]) for row in cells) for k in range(len(hdr))]
        A("\n".join("  ".join(c.rjust(w[k]) if k > 1 and k < 9 else c.ljust(w[k]) for k, c in enumerate(row)) for row in cells))
    A("")
    A("reach5 rows are SHARES (the difference is in share points); fwd20 / mfe10 / mfe20 are in ADR units of the level.")
    return "\n".join(L) + "\n"


# ═══ run ════════════════════════════════════════════════════════════════════════════════════════════
def make_bars(data: Path):
    """(`bars(ticker)`, last calendar index) from the data dir's daily export - the runner's own loader."""
    D = runner.load_daily(data / "daily_closes_all.csv.gz")

    def bars(t):
        k = D.tid.get(t)
        if k is None:
            return None
        a, b = int(D.start[k]), int(D.stop[k])
        return D.ci[a:b], D.h[a:b], D.c[a:b]

    return bars, len(D.cal) - 1


def run_read(data: Path, out: Path | None = None, bars=None, cal_last_ci: int | None = None, levels: tuple = LEVELS) -> dict:
    out = out or data / "out"
    if bars is None:
        bars, cal_last_ci = make_bars(data)
    picks = pd.read_csv(out / "selection_picks.tsv", sep="\t", keep_default_na=False)
    ca = pd.read_csv(out / "selection_controls_a.tsv", sep="\t", keep_default_na=False)
    cb = pd.read_csv(out / "selection_controls_b.tsv", sep="\t", keep_default_na=False)
    picks["ticker"] = picks["symbol"]
    results = {}
    for lv in levels:
        results[lv] = compare_level(picks[picks["level"] == lv], ca[ca["level"] == lv], cb[cb["level"] == lv], lv, bars, cal_last_ci)
    txt = result_text(results)
    (out / "selection_result.txt").write_text(txt)
    pd.DataFrame([x for r in results.values() for x in r["rows"]]).to_csv(out / "selection_result.tsv", sep="\t", index=False)
    return {"text": txt, "results": results}


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--data", default=str(PRE), help="the Alpaca-era data dir (default /Users/alvinfung/apollo_data/cb702_pre)")
    ap.add_argument("--out", help="where selection_picks.tsv etc. are and where the result is written (default DATA/out)")
    args = ap.parse_args(argv)
    print(run_read(Path(args.data), Path(args.out) if args.out else None)["text"])


if __name__ == "__main__":
    main()
