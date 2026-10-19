#!/usr/bin/env python3
"""#702 selection test - BUILD + POPULATION ONLY (docs/analysis/cb_selection_test_prereg_2026-10-19.md). No outcome is computed here.

Two stages, both $0 (local files only, no network, no DB, no module edit):

  export  the Alpaca-era (2016-01..2022-06) daily export in the runner's input format, written OUTSIDE the repo under
          /Users/alvinfung/apollo_data/cb702_pre/ (mirrors cb702/'s layout): split-adjusted OHLCV (`daily_closes_all.csv.gz`), the RAW close per
          bar (`daily_raw_close.csv.gz`, for the $5 floor), the identity-break table (`symbol_guard.tsv`), `small_pulls.psv` and
          `cb702_sic.psv` (copied: a symbol with no type is admitted as unknown and COUNTED by the daily stage), `sessions.txt`.
          The bars are `qm_streams/ext_2016_2022/alp_flat.npz` (the `ext_bars.py` cache: zero-volume forward-fills already dropped), minus
          any bar off the SPY calendar (the runner refuses those).
  join    reads the daily stage's `candidates_<keys>.tsv` / `watch_<keys>.tsv.gz` (run with `--no-close-variant`: no outcome of any
          kind) and writes the PICKS, the two CONTROLS and the POPULATION REPORT. KEYS ONLY: the candidate file is read through a
          column whitelist that holds no price of the breakout day or after (the level `pivot` and `adr20` are fixed on the night
          BEFORE E), so a post-E price cannot enter this stage by accident.

  python scripts/probes/_cb_backtest/selection_pre.py export
  python scripts/probes/_cb_backtest/runner.py daily --data /Users/alvinfung/apollo_data/cb702_pre --keys tl,com --no-close-variant \\
      --raw-close /Users/alvinfung/apollo_data/cb702_pre/daily_raw_close.csv.gz --breaks /Users/alvinfung/apollo_data/cb702_pre/symbol_guard.tsv \\
      --watch-start 2017-03-01 --watch-end 2021-12-31 --era-label pre --out /Users/alvinfung/apollo_data/cb702_pre/out \\
      --small-out /Users/alvinfung/apollo_data/cb702_pre/out/small
  python scripts/probes/_cb_backtest/selection_pre.py join

DEFINITIONS (the pre-registration's, made exact here):
  * a PICK BASE = a distinct (bars_symbol, w_pole_date) of `labelled_candidates_ext.tsv` with source == stream, hq == 1,
    status_at_ref == in_base_at_ref (330). Its TALK DATE = the earliest ref_date among its in-base talks; `ref_date_max` (the latest) is
    written beside and `E_after_last_talk` says whether the first break also clears the latest talk (the main loop decides which date
    rules; this stage does not).
  * the pick is matched, PER LEVEL (tl = the registered level, com beside), to the BASE of the pre run that holds a pole within 3 sessions
    of w_pole_date (the chain key's own tolerance; the nearest pole if several bases qualify), and to that base's FIRST C0 breakout
    (`first_chain_C0 == 1`). It is kept only if that breakout day E is STRICTLY AFTER the talk date.
  * CONTROL (a) = every other level-K first breakout whose E is in the same calendar month as some pick's E; CONTROL (b) = the other
    level-K first breakouts of the pick tickers in the era. "Other" = not a talked base: every base matched to ANY of the 330 pick bases
    (kept or lost) is out of both controls, so a base he discussed after it broke out cannot pose as a control.
"""
from __future__ import annotations

import argparse
import bisect
import csv
import datetime as dt
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts" / "probes" / "_qm_streams"))

from agents.market_intelligence import consolidation_breakout as cb  # noqa: E402  (read-only: chain_bases, POLE_DRIFT_MAX)

CB_DATA = Path("/Users/alvinfung/apollo_data/cb702")
EXT = CB_DATA / "qm_streams" / "ext_2016_2022"
PRE = Path("/Users/alvinfung/apollo_data/cb702_pre")
LABELS = EXT / "labelled_candidates_ext.tsv"
FRAMES = CB_DATA / "qm_streams" / "vision" / "p4b_label_lines.tsv"
WATCH_FIRST, WATCH_LAST = dt.date(2017, 3, 1), dt.date(2021, 12, 31)
LEVELS = ("tl", "com")                              # tl = the registered level; com beside (the brief)
POLE_TOL = cb.POLE_DRIFT_MAX                        # 3 sessions: the chain key's own drift tolerance

# The ONLY candidate columns the join reads. None is a price of the breakout day or later; `pivot` (the level, projected to E from bars
# up to D) and `adr20` (as of D = E-1) are fixed before E opens. Anything else in the file is never loaded.
CAND_COLS = ["ticker", "D", "E", "K", "pole_date", "pole_ci", "base_id", "retrigger_chain", "first_chain_C0", "pivot", "adr20"]
WATCH_COLS = ["ticker", "watch_date", "ci", "pole_date", "pole_ci", "pivot_tl", "pivot_com"]


# ═══ export ════════════════════════════════════════════════════════════════════════════════════
def export(pre: Path = PRE, ext: Path = EXT, cb_data: Path = CB_DATA) -> dict:
    import ext_bars

    pre.mkdir(parents=True, exist_ok=True)
    a = ext_bars.load(str(ext))
    cal = ext_bars._calendar(a)                                         # SPY's sessions: the runner's calendar
    stats = {"alp_flat_rows": len(a["d"]), "alp_symbols": len(a["tickers"]), "sessions": len(cal),
             "first_session": dt.date.fromordinal(int(cal[0])).isoformat(), "last_session": dt.date.fromordinal(int(cal[-1])).isoformat()}
    assert (np.diff(cal) > 0).all()
    ci = np.searchsorted(cal, a["d"])
    on_cal = (ci < len(cal)) & (cal[np.minimum(ci, len(cal) - 1)] == a["d"])
    stats["off_calendar_bars_dropped"] = int((~on_cal).sum())
    assert (a["v"] > 0).all(), "a zero-volume row survived into the cache (ext_bars drops them)"
    assert (a["c_raw"] > 0).all() and np.isfinite(a["c_raw"]).all()
    tick = np.repeat(a["tickers"], a["stop"] - a["start"])
    keep = on_cal
    tick, d = tick[keep], a["d"][keep]
    # the runner asserts SPY and QQQ carry EVERY session (the phase join is by date): check it before writing 10M rows
    for sym in ("SPY", "QQQ"):
        assert np.array_equal(d[tick == sym], cal), f"{sym} does not carry every SPY session"
    stats["rows_written"] = int(keep.sum())
    stats["symbols_written"] = int(len(np.unique(tick)))
    days = (d - 719163).astype("datetime64[D]").astype(str)
    cols = {"ticker": tick, "d": days}
    daily = pd.DataFrame({**cols, **{k: a[k][keep] for k in ("o", "h", "l", "c", "v")}})
    gz = {"method": "gzip", "compresslevel": 3}
    daily.to_csv(pre / "daily_closes_all.csv.gz", header=False, index=False, compression=gz)
    pd.DataFrame({**cols, "c_raw": a["c_raw"][keep]}).to_csv(pre / "daily_raw_close.csv.gz", header=False, index=False, compression=gz)
    (pre / "sessions.txt").write_text("\n".join(dt.date.fromordinal(int(x)).isoformat() for x in cal) + "\n")
    # identity guard, re-derived from the arrays (hole / jump rules; the Polygon-overlap flags are not needed for the breaks) and checked
    # against the table the P4b extension used, so the guard of this run IS the guard that produced the label set
    rows, _brk = ext_bars.guard(a, {})
    ext_bars.write_guard(rows, str(pre))
    old = {r["symbol"]: r["breaks"] for r in csv.DictReader(open(ext / "symbol_guard.tsv"), delimiter="\t")}
    new = {s: r["breaks"] for s, r in rows.items()}
    bad = [s for s in set(old) | set(new) if old.get(s, "") != new.get(s, "")]
    stats["symbols_with_a_break"] = sum(1 for v in new.values() if v)
    stats["guard_breaks_differing_from_ext_table"] = len(bad)
    assert not bad, f"re-derived identity breaks differ from the P4b table for {len(bad)} symbols, e.g. {sorted(bad)[:5]}"
    for name in ("small_pulls.psv", "cb702_sic.psv"):
        shutil.copyfile(cb_data / name, pre / name)
    with open(pre / "export_stats.tsv", "w") as f:
        for k, v in stats.items():
            f.write(f"{k}\t{v}\n")
    return stats


# ═══ join ══════════════════════════════════════════════════════════════════════════════════════
def pick_bases(labels_path: Path = LABELS) -> pd.DataFrame:
    """One row per distinct pick base: (symbol, pole_date) with talk_date = earliest in-base ref_date, ref_date_max = the latest, n_talks,
    spoken ticker(s), the first_E ext_c0 recorded on the earliest talk (cross-check column), last_watch of that talk."""
    df = pd.read_csv(labels_path, sep="\t", keep_default_na=False, low_memory=False,
                     usecols=["source", "ticker", "ref_date", "hq", "bars_symbol", "status_at_ref", "w_pole_date", "first_E", "last_watch",
                              "bars_source"])
    s = df[(df["source"] == "stream") & (df["hq"] == 1) & (df["status_at_ref"] == "in_base_at_ref")].copy()
    s = s.sort_values(["bars_symbol", "w_pole_date", "ref_date"], kind="stable")
    g = s.groupby(["bars_symbol", "w_pole_date"], sort=True)
    out = g.agg(talk_date=("ref_date", "min"), ref_date_max=("ref_date", "max"), n_talks=("ref_date", "size"),
                spoken=("ticker", lambda x: "|".join(sorted(set(x)))), ext_first_E=("first_E", "first"),
                ext_last_watch=("last_watch", "first"), bars_source=("bars_source", "first")).reset_index()
    out = out.rename(columns={"bars_symbol": "symbol", "w_pole_date": "pole_date"})
    return out


def frame_bases(frames_path: Path = FRAMES) -> set:
    """The frame-verified bases ('TICKER|pole_date', on the SPOKEN ticker)."""
    d = pd.read_csv(frames_path, sep="\t", keep_default_na=False, usecols=["frame_id", "base"])
    return set(d["base"])


def read_sessions(pre: Path) -> list:
    return [dt.date.fromisoformat(x) for x in (pre / "sessions.txt").read_text().split()]


def classify_pick(pick: dict, level: str, *, sessions_ci: dict, watch_by_sym: dict, bases_of_poles: dict, cands_by_base: dict,
                  symbols: set, win: tuple, end_ci: int) -> dict:
    """One pick base x one level -> its match (or its loss reason). Priority, first that holds:
    symbol_not_in_export | talk_outside_window | no_base_in_pre_run | no_level_in_base | open_at_window_end | never_broke_out |
    break_before_talk | matched."""
    sym, pole = pick["symbol"], pick["pole_date"]
    res = dict(symbol=sym, pole_date=pole, level=level, talk_date=pick["talk_date"], ref_date_max=pick["ref_date_max"],
               n_talks=pick["n_talks"], reason="", base_id="", E="", D="", pivot="", adr20="", E_ci="", n_candidate_bases="",
               E_after_last_talk="")
    talk = pick["talk_date"]
    if sym not in symbols:
        res["reason"] = "symbol_not_in_export"
        return res
    if not (win[0].isoformat() <= talk <= win[1].isoformat()):
        res["reason"] = "talk_outside_window"
        return res
    pci = sessions_ci.get(pole)
    rows = watch_by_sym.get(sym)
    near = [] if rows is None or pci is None else [r for r in rows if abs(r[0] - pci) <= POLE_TOL]
    if not near:
        res["reason"] = "no_base_in_pre_run"
        return res
    bases = sorted({bases_of_poles[(sym, r[0])] for r in near})
    res["n_candidate_bases"] = len(bases)
    # the base whose nearest pole is closest to the pick's pole (ties: the earlier pole)
    best = min(near, key=lambda r: (abs(r[0] - pci), r[0]))
    base = bases_of_poles[(sym, best[0])]
    res["base_id"] = base
    base_rows = [r for r in rows if bases_of_poles[(sym, r[0])] == base]
    if not any(r[2 if level == "tl" else 3] for r in base_rows):
        res["reason"] = "no_level_in_base"                      # no night of the base carried this level (tl: no down-sloping line)
        return res
    c = cands_by_base.get((base, level))
    if c is None:
        res["reason"] = "open_at_window_end" if max(r[1] for r in base_rows) >= end_ci else "never_broke_out"
        return res
    res.update(D=c["D"], E=c["E"], pivot=c["pivot"], adr20=c["adr20"], E_ci=sessions_ci.get(c["E"], ""))
    if not c["E"] > talk:
        res["reason"] = "break_before_talk"
        return res
    res["reason"] = "matched"
    res["E_after_last_talk"] = int(c["E"] > pick["ref_date_max"])
    return res


def build_population(cands: pd.DataFrame, watch: pd.DataFrame, picks: pd.DataFrame, sessions: list, frames: set,
                     symbols: set, win: tuple = (WATCH_FIRST, WATCH_LAST), levels: tuple = LEVELS) -> dict:
    """The whole join as a pure function of in-memory tables -> {'rows': per pick x level, 'controls_a', 'controls_b', ...}."""
    sessions_ci = {d.isoformat(): k for k, d in enumerate(sessions)}
    end_ci = bisect.bisect_right(sessions, win[1]) - 1                 # the last night the daily stage scanned
    # chain bases over EVERY watch row, exactly as the runner stamps them (ticker, pole_ci, pole_date)
    bo = cb.chain_bases(zip(watch["ticker"], watch["pole_ci"].astype(int), watch["pole_date"]))
    watch_by_sym = defaultdict(list)                     # symbol -> [(pole_ci, ci, has_tl, has_com)]
    for t, pc, ci, ptl, pcom in zip(watch["ticker"], watch["pole_ci"].astype(int), watch["ci"].astype(int),
                                    watch["pivot_tl"].notna(), watch["pivot_com"].notna()):
        watch_by_sym[t].append((pc, ci, bool(ptl), bool(pcom)))
    first = cands[(cands["first_chain_C0"] == 1)]
    cands_by_base = {(r["base_id"], r["K"]): r for r in first.to_dict("records")}
    assert len(cands_by_base) == len(first), "a base has two first C0 breakouts at one level"
    rows = []
    for p in picks.to_dict("records"):
        for level in levels:
            rows.append(classify_pick(p, level, sessions_ci=sessions_ci, watch_by_sym=watch_by_sym, bases_of_poles=bo,
                                      cands_by_base=cands_by_base, symbols=symbols, win=win, end_ci=end_ci))
    res = pd.DataFrame(rows)
    spoken = {(r["symbol"], r["pole_date"]): r["spoken"] for r in picks.to_dict("records")}
    res["frame_verified"] = [int(any(f"{t}|{r.pole_date}" in frames for t in {r.symbol, *spoken[(r.symbol, r.pole_date)].split("|")}))
                             for r in res.itertuples()]
    res["ext_first_E"] = [picks.set_index(["symbol", "pole_date"]).loc[(r.symbol, r.pole_date), "ext_first_E"] for r in res.itertuples()]
    talked = set(res.loc[res["base_id"] != "", "base_id"])
    out = {"rows": res, "talked_bases": talked}
    ca, cbb = {}, {}
    for level in levels:
        kept = res[(res["level"] == level) & (res["reason"] == "matched")]
        allfirst = first[first["K"] == level].copy()
        allfirst["month"] = allfirst["E"].str[:7]
        allfirst["E_ci"] = allfirst["E"].map(sessions_ci)
        others = allfirst[~allfirst["base_id"].isin(talked)]
        months = set(kept["E"].str[:7])
        ca[level] = others[others["month"].isin(months)].copy()
        cbb[level] = others[others["ticker"].isin(set(kept["symbol"]))].copy()
        out[f"all_first_{level}"] = allfirst
    out["controls_a"], out["controls_b"] = ca, cbb
    return out


# ═══ cross-check against the P4b label run ═══════════════════════════════════════════════════════
def crosscheck_ext(picks: pd.DataFrame, xcands: pd.DataFrame, last_watch_date: str, first_watch_date: str = WATCH_FIRST.isoformat()) -> dict:
    """The pre run (this stage's bars + runner options) against the label run that produced `labelled_candidates_ext.tsv` (`ext_c0.py` on
    the SAME bars with the SAME module): for every pick base, the earliest breakout day E over the registered four levels (k5/k10/full/tl) of
    the SPEC-key base (ticker, pole_date) with D >= the base's last watch night in the talk window - ext's own definition of `first_E` - read
    from a default-keys run of the same options (`out_xcheck/`). A disagreement is a bug in the export / the runner options / this join,
    not a finding. `last_watch_date` / `first_watch_date` = the first and last watch night of the pre run: an ext break outside them cannot be
    seen and is counted apart."""
    by = defaultdict(list)
    for t, pole, d, e in zip(xcands["ticker"], xcands["pole_date"], xcands["D"], xcands["E"]):
        by[(t, pole)].append((d, e))
    cnt = Counter()
    bad = []
    for p in picks.to_dict("records"):
        ext = p["ext_first_E"] or ""
        lw = p["ext_last_watch"]
        mine = [e for d, e in by.get((p["symbol"], p["pole_date"]), []) if d >= lw]
        mine = min(mine) if mine else ""
        if ext and mine:
            k = "agree" if ext == mine else "differ"
        elif not ext and not mine:
            k = "both_none"
        elif ext and not mine:
            k = ("ext_break_past_window_end" if ext > last_watch_date else
                 "ext_break_before_window_start" if ext < first_watch_date else "ext_has_break_mine_none")
        else:
            k = "mine_has_break_ext_none"
        cnt[k] += 1
        if k in ("differ", "ext_has_break_mine_none", "mine_has_break_ext_none"):
            bad.append((p["symbol"], p["pole_date"], ext, mine))
    return {"counts": dict(cnt), "bad": bad}


def matched_vs_ext(res: pd.DataFrame, level: str = "tl") -> dict:
    """The MATCHED picks' first break E (the chain base's first C0 break at `level`) against the first_E the label run recorded for the same base
    (its SPEC-key base, any of the four registered levels, D >= the last watch night in the talk window). They need not agree - that is the
    point of the chain key (a pole that drifts 1-3 sessions is one base) and of the level - so this is a description, not a test:
    same | ext_blank (the spec-key base never broke; a pole-drift sibling did) | ext_earlier (another level broke first) | ext_later."""
    m = res[(res["level"] == level) & (res["reason"] == "matched")]
    c = Counter()
    for e, x in zip(m["E"], m["ext_first_E"]):
        c["same" if x == e else "ext_blank" if not x else "ext_earlier" if x < e else "ext_later"] += 1
    return dict(c)


# ═══ population report ═══════════════════════════════════════════════════════════════════════════
def _tab(rows: list, header: list) -> str:
    cells = [header] + [[str(x) for x in r] for r in rows]
    w = [max(len(r[k]) for r in cells) for k in range(len(header))]
    return "\n".join("  ".join(c.rjust(w[k]) if k else c.ljust(w[k]) for k, c in enumerate(r)) for r in cells)


REASONS = ["matched", "break_before_talk", "never_broke_out", "open_at_window_end", "no_level_in_base", "no_base_in_pre_run",
           "talk_outside_window", "symbol_not_in_export"]
REASON_NOTE = {
    "matched": "kept: the level's first C0 breakout is STRICTLY AFTER the talk date",
    "break_before_talk": "dropped: that base's first break is on or before the talk (hindsight)",
    "never_broke_out": "dropped: the base lapsed inside the window with no break at this level",
    "open_at_window_end": "dropped: the base was still in place on the last scanned night (2021-12-31); a break after it is not seen",
    "no_level_in_base": "dropped: no night of the base carried this level (tl needs a down-sloping line)",
    "no_base_in_pre_run": "dropped: no pre-run watch night with a pole within 3 sessions of the label's pole",
    "talk_outside_window": "dropped: the earliest talk is outside 2017-03-01..2021-12-31",
    "symbol_not_in_export": "dropped: the symbol has no Alpaca series",
}


def break_gap_table(lost: pd.DataFrame, sessions: list) -> str:
    """The `break_before_talk` bases by SESSIONS between their first break and the talk (<= 5 / 6-20 / > 20) against what the label run recorded
    as `first_E` on the earliest talk (blank = it saw no break at or after the last watch night inside the talk's 28-day window; 'after the talk' =
    it saw a later one). The label run called every one of these in_base_at_ref; the registered rule here is stricter (the first C0 break of the
    whole chain base), so the split is what a ruling on 'discussed after it broke out' needs."""
    rows = {b: [0, 0] for b in ("<= 5 sessions", "6-20 sessions", "> 20 sessions")}
    for e_ci, talk, ext in zip(lost["E_ci"], lost["talk_date"], lost["ext_first_E"]):
        gap = bisect.bisect_right(sessions, dt.date.fromisoformat(talk)) - 1 - int(e_ci)
        rows["<= 5 sessions" if gap <= 5 else "6-20 sessions" if gap <= 20 else "> 20 sessions"][0 if not ext else 1] += 1
    return _tab([[b, v[0], v[1], v[0] + v[1]] for b, v in rows.items()], ["break to talk", "label run: no break seen", "label run: break after talk", "bases"])


def population_text(pop: dict, picks: pd.DataFrame, labels_n: dict, small: Path, xcheck: dict, win: tuple = (WATCH_FIRST, WATCH_LAST),
                    sessions: "list | None" = None) -> str:
    res = pop["rows"]
    L = []
    A = L.append
    A("#702 SELECTION TEST - POPULATION (built before any outcome; NO forward return, MFE, R or post-E price was read or printed)")
    A(f"pre run: Alpaca-era split-adjusted daily bars, watch nights D {win[0]}..{win[1]}, C0 rules of the frozen module, levels tl (registered) + com")
    A("")
    A("1. THE LABEL SET")
    A(f"  talks: stream, hq = 1, in_base_at_ref: {labels_n['talks']:,} rows -> {len(picks):,} distinct stock-bases (bars_symbol + w_pole_date)")
    tp = Counter(picks["n_talks"])
    A("  talks per base: " + ", ".join(f"{k}: {v}" for k, v in sorted(tp.items()) if k <= 6)
      + (f", 7+: {sum(v for k, v in tp.items() if k > 6)}" if any(k > 6 for k in tp) else "") + "   (talks: bases)")
    A("  bases by year of the EARLIEST talk: " + ", ".join(f"{y}: {n}" for y, n in sorted(Counter(picks['talk_date'].str[:4]).items())))
    A(f"  renamed symbols (the Alpaca symbol differs from the spoken ticker): {int((picks['spoken'] != picks['symbol']).sum())} bases")
    for level in LEVELS:
        r = res[res["level"] == level]
        kept = r[r["reason"] == "matched"]
        A("")
        A(f"2. PICKS - level {level}" + ("  (the registered level)" if level == LEVELS[0] else "  (beside)"))
        c = Counter(r["reason"])
        A(_tab([[k, c.get(k, 0), REASON_NOTE[k]] for k in REASONS], ["outcome", "bases", "meaning"]))
        A(f"  total {sum(c.values())}  (= {len(picks)} pick bases)")
        A("  matched by year of E: " + (", ".join(f"{y}: {n}" for y, n in sorted(Counter(kept['E'].str[:4]).items())) or "none"))
        A("  matched by month of E: " + (", ".join(f"{m}: {n}" for m, n in sorted(Counter(kept['E'].str[:7]).items())) or "none"))
        A(f"  matched picks: {len(kept)}   (the registration expected roughly 100-250 of the {len(picks)}: "
          f"{'BELOW the floor of that range' if len(kept) < 100 else 'inside that range'}; n < 30 would be CAN'T TELL whatever the interval says)")
        A(f"  frame-verified subset (bases in vision/p4b_label_lines.tsv): {int(kept['frame_verified'].sum())} of the matched picks "
          f"({int(r['frame_verified'].sum())} of {len(picks)} pick bases carry the flag at all)")
        A(f"  sensitivity to WHICH talk date rules: {int((kept['E_after_last_talk'] == 0).sum())} matched picks have a first break on or "
          f"before their LAST talk (kept on the earliest talk, dropped if the latest ruled); {int((kept['n_talks'] > 1).sum())} matched picks have 2+ talks")
        multi = kept[kept["n_candidate_bases"].astype(int) > 1]
        A(f"  picks with 2+ pre-run bases inside the +-3 session pole tolerance (nearest used): {len(multi)}")
        lost_bb = r[r["reason"] == "break_before_talk"]
        gap = (pd.to_datetime(lost_bb["talk_date"]) - pd.to_datetime(lost_bb["E"])).dt.days
        A(f"  of the {len(lost_bb)} 'break_before_talk' bases, {int((gap <= 5).sum())} broke within 5 calendar days before the talk")
        if sessions is not None and len(lost_bb):
            A("  the rule is the registered one (the FIRST C0 break of the whole base, whatever came after); a base that broke, failed and re-formed is "
              "dropped here. Whether that counts as 'discussed after it broke out' is for the ruling BEFORE the read:")
            A(break_gap_table(lost_bb, sessions))
    A("")
    A("3. CONTROLS (a talked base = any base matched to one of the pick bases, kept or lost, is excluded from both)")
    for level in LEVELS:
        kept = res[(res["level"] == level) & (res["reason"] == "matched")]
        allf = pop[f"all_first_{level}"]
        ca, cbb = pop["controls_a"][level], pop["controls_b"][level]
        months = sorted(set(kept["E"].str[:7]))
        cam = Counter(ca["month"])
        pm = Counter(kept["E"].str[:7])
        A(f"  level {level}: all first-C0 breakouts in the era {len(allf):,}; talked bases among them {int(allf['base_id'].isin(pop['talked_bases']).sum())}")
        A(f"    control (a) same-month first breakouts: {len(ca):,} over {len(cam)} of {len(months)} pick months"
          f" (median {int(np.median(list(cam.values()))) if cam else 0} per month; picks in a month with no control: "
          f"{sum(n for m, n in pm.items() if m not in cam)})")
        pk_tickers = set(kept["symbol"])
        cbt = Counter(cbb["ticker"])
        A(f"    control (b) other first breakouts of the pick tickers: {len(cbb):,} over {len(cbt)} of {len(pk_tickers)} pick tickers"
          f" (picks whose ticker has no other base: {int(sum(1 for s in kept['symbol'] if s not in cbt))})")
    A("")
    A("4. UNIVERSE (the daily stage's own tables; RS percentiles are over Alpaca's symbol list - survivorship-biased: Alpaca omits many delisted names)")
    ud = pd.read_csv(small / "universe_by_date_tl_com.tsv", sep="\t", usecols=["date", "universe_n", "watch_rows"])
    ud["year"] = ud["date"].str[:4]
    A(_tab([[y, len(g), int(g["universe_n"].min()), int(g["universe_n"].median()), int(g["universe_n"].max()), int(g["watch_rows"].sum())]
            for y, g in ud.groupby("year")], ["year", "nights", "universe min", "median", "max", "watch rows"]))
    gc = pd.read_csv(small / "gate_counts_tl_com.tsv", sep="\t")
    gcs = gc.set_index("stage")
    yrs = [c for c in gc.columns if c.isdigit()]
    A("  nights not evaluated, by year (ticker-nights):")
    A(_tab([[st] + [int(gcs.loc[st, y]) for y in yrs] + [int(gcs.loc[st, "total"])] for st in ("identity_break", "history", "universe_fail")],
           ["reason"] + yrs + ["total"]))
    ut = pd.read_csv(small / "universe_types_tl_com.tsv", sep="\t")
    A("  universe members with NO security type (admitted as unknown, as prod does; nights / distinct tickers):")
    A(_tab([[int(r.year), int(r.unknown_type_nights), int(r.unknown_type_tickers)] for r in ut.itertuples()], ["year", "nights", "tickers"]))
    A("")
    A("5. CROSS-CHECK against the P4b label run (same bars, same module; default-keys run in out_xcheck/)")
    A("  earliest break over k5/k10/full/tl of the base (ticker, pole_date) at or after its last watch night, against the first_E ext_c0 recorded:")
    A(_tab([[k, v] for k, v in sorted(xcheck["counts"].items())], ["result", "bases"]))
    if xcheck["bad"]:
        A("  first disagreements (symbol, pole_date, ext first_E, mine): " + "; ".join(str(b) for b in xcheck["bad"][:8]))
    mv = matched_vs_ext(res)
    A("  the MATCHED tl picks' chain-base first break against that same first_E (a description, not a test - the chain key merges drifting poles):")
    A(_tab([[k, v] for k, v in sorted(mv.items())], ["result", "picks"]))
    A("")
    A("6. WHAT THIS STAGE READ")
    A(f"  candidates: only {', '.join(CAND_COLS)} (level and ADR20 are fixed on the night BEFORE E); watch: only {', '.join(WATCH_COLS)}. "
      "No bar after a breakout day was opened; the daily stage ran with --no-close-variant.")
    return "\n".join(L) + "\n"


# ═══ run ════════════════════════════════════════════════════════════════════════════════════════
def load_candidates(path: Path) -> pd.DataFrame:
    """The candidates table through the column WHITELIST: nothing outside `CAND_COLS` is ever parsed (the file also holds the open / high / low /
    close / volume of the breakout day, which this stage must not read)."""
    return pd.read_csv(path, sep="\t", usecols=CAND_COLS, keep_default_na=False,
                       dtype={"ticker": str, "D": str, "E": str, "K": str, "pole_date": str, "base_id": str})


def load_watch(path: Path) -> pd.DataFrame:
    """The watch table through the column whitelist `WATCH_COLS` (a blank level reads as NaN: that night had no such level)."""
    return pd.read_csv(path, sep="\t", usecols=WATCH_COLS, keep_default_na=False, na_values=[""],
                       dtype={"ticker": str, "watch_date": str, "pole_date": str})


def run_join(pre: Path = PRE) -> dict:
    out = pre / "out"
    sfx = "_" + "_".join(LEVELS)
    cands = load_candidates(out / f"candidates{sfx}.tsv")
    watch = load_watch(out / f"watch{sfx}.tsv.gz")
    sessions = read_sessions(pre)
    symbols = {r["symbol"] for r in csv.DictReader(open(pre / "symbol_guard.tsv"), delimiter="\t")}
    picks = pick_bases()
    labels = pd.read_csv(LABELS, sep="\t", keep_default_na=False, usecols=["source", "hq", "status_at_ref"], low_memory=False)
    labels_n = {"talks": int(((labels["source"] == "stream") & (labels["hq"] == 1) & (labels["status_at_ref"] == "in_base_at_ref")).sum())}
    frames = frame_bases()
    pop = build_population(cands, watch, picks, sessions, frames, symbols)
    # sanity: for tl / com a first break is C0 by construction, so "first C0" and "first of the chain" are the same row
    for level in LEVELS:
        k = cands[cands["K"] == level]
        assert int((k["retrigger_chain"] == 0).sum()) == int((k["first_chain_C0"] == 1).sum()), f"{level}: first-C0 differs from first-of-chain"
    xc = pd.read_csv(pre / "out_xcheck" / "candidates.tsv", sep="\t", usecols=["ticker", "pole_date", "D", "E"], keep_default_na=False,
                     dtype=str)
    xcheck = crosscheck_ext(picks, xc, WATCH_LAST.isoformat())
    res = pop["rows"]
    res["month"] = res["E"].str[:7]
    res.to_csv(out / "selection_picks_all.tsv", sep="\t", index=False)
    keep_cols = ["symbol", "pole_date", "level", "base_id", "talk_date", "ref_date_max", "n_talks", "D", "E", "E_ci", "month", "pivot", "adr20",
                 "frame_verified", "E_after_last_talk", "n_candidate_bases", "ext_first_E"]
    res[res["reason"] == "matched"][keep_cols].to_csv(out / "selection_picks.tsv", sep="\t", index=False)
    ctl_cols = ["K", "ticker", "base_id", "pole_date", "D", "E", "E_ci", "month", "pivot", "adr20"]
    for name in ("controls_a", "controls_b"):
        d = pd.concat([pop[name][lv][ctl_cols] for lv in LEVELS], ignore_index=True).rename(columns={"K": "level"})
        d.to_csv(out / f"selection_{name}.tsv", sep="\t", index=False)
    txt = population_text(pop, picks, labels_n, out / "small", xcheck, sessions=sessions)
    (out / "selection_population.txt").write_text(txt)
    return {"text": txt, "pop": pop, "xcheck": xcheck}


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("stage", choices=["export", "join"])
    ap.add_argument("--pre", default=str(PRE), help="the Alpaca-era data dir (default /Users/alvinfung/apollo_data/cb702_pre)")
    args = ap.parse_args(argv)
    if args.stage == "export":
        for k, v in export(Path(args.pre)).items():
            print(f"{k}\t{v}", flush=True)
    else:
        print(run_join(Path(args.pre))["text"])


if __name__ == "__main__":
    main()

