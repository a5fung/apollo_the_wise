#!/usr/bin/env python3
"""#705 — QULLAMAGGIE REPLAY 03 (round 3): the structural stop, holding winners longer, market-strength sizing. His 236 stream calls
(era A; era B 9 descriptive) and the same day's other breakouts, re-walked under three levers fixed before this run, on top of the
30% position cap (docs/analysis/cb_qm_replay_round3_prereg_2026-10-24.md). Registration only until the freeze; the real run happens
ONCE after it.

The frozen first replay (01_replay.py, c4478588…) and the frozen second (02_execution_variants.py, 346516fb…) are IMPORTED read-only
through the second (one import path, one copy of each): the loaders, populations, walk wiring, trade builder, account simulation,
control draw, date-matched difference, G8, the line-anchored freeze lock, the parity readers, the own-low flag and the fork function.
Nothing in either is edited. The runner's walkers (`cb.entry_variants`, `cb.day0_walk`, `cb.walk_arms`, `cb.forward_window`) are
called unchanged.

What it does (the registration's §4-§7, nothing else; every variant at the 30% cap = the first read's `cap_30` row, 2.044):
  B0          the baseline, re-walked: ORH5, the module's low of the day at the fill, too-wide skipped, exit p33_s3_t10, 1% risk /
              30% cap / 30% per stock. A BASELINE-PARITY GATE: B0's trades (two exit arms), account curve, band, re-entry count and
              date-matched line must equal the first read's stored outputs before any variant number is printed.
  W1          the STRUCTURAL stop: the ORH5 fill with the stop at the base low at D (the module's `base_low`, from daily bars up to D;
              no one-ADR skip; the 20 too-wide calls fill too), the day-0 walk re-run on it, sized at 1% risk (wider stop = smaller
              position). BESIDE W1b: the LOWER of the day low through the minute BEFORE the fill minute and one ADR20 below the fill.
  W2          hold winners longer: after the day-3 partial and the breakeven move, trail on the 20-day average, or the 10-day when
              ADR20 at D is above the module's speed cut 4.79% (`cb.HIS_EXIT_ARMS["d3_p33_tspd"]`). BESIDE: the plain 20-day
              (`p33_s3_t20`, seen at the 20% cap in the first read) and no partial at all, the whole position on the 10-day
              (`trail10_only`).
  W3          market-strength sizing: risk 1% when QQQ at D is above both its 10- and 20-day averages, 0.5% otherwise. BESIDE W3b: no
              trade when QQQ is below both.
  COMBINED    W1's stop x W2's exit x W3's sizing at the 30% cap: the fork variant.
  W4          BESIDE ONLY, B, decides nothing: margin up to 2x gross (a trade may borrow up to one times the previous close's equity),
              and one add per trade on a new high after the day-3 partial.
  Every variant is applied to the control too; the band reuses the FIRST READ'S 200 same-day draws (same seed, same key).
  FORK        written before any outcome: COMBINED returns >= +50% in BOTH 2020 and 2021 AND at most 5% of the band's draws end at or
              above his final equity -> EXPLAINED; otherwise -> NEXT GAPS (the EPs and parabolic shorts in his record; the trades he
              never mentioned on stream; adds / margin if still beside). Never "the setup does not work".

No subagent, no DB, no network. Read-only on every input. Nothing dated after 2024-12-31 is kept from any era-B file.

Run:  python3 scripts/probes/_705_qm_replay_1023/03_round3.py --dry-run   (loads, asserts the populations, reads the base low at D from
                                                    bars up to D and cross-checks it against the stored base_depth, checks minute
                                                    coverage from the fetch logs, prints the pins; opens NO minute file, calls NO entry
                                                    or exit function, reads NO outcome file, computes NO outcome)
      python3 scripts/probes/_705_qm_replay_1023/03_round3.py             (the REAL run: refuses (exit 2) unless every pin incl. the
                                                    doc-body hash sits under the doc's one line-anchored freeze marker line, or if any
                                                    output exists)
"""
from __future__ import annotations

import argparse
import bisect
import gzip
import importlib.util
import math
import os
import sys
import time
import zlib
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
SECOND_PATH = os.path.join(HERE, "02_execution_variants.py")


def _load_second():
    """The FROZEN second read (pinned 346516fb…), imported read-only; it imports the frozen first read (c4478588…) once itself."""
    spec = importlib.util.spec_from_file_location("_705_exec02_frozen", SECOND_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_705_exec02_frozen"] = mod
    spec.loader.exec_module(mod)
    return mod


ex = _load_second()
rp, R, cb, FIT = ex.rp, ex.R, ex.cb, ex.FIT

# ═════════════════════════════════════════════════════════════════════════════════════════════
# paths and pins
# ═════════════════════════════════════════════════════════════════════════════════════════════
DOC = os.path.join(REPO, "docs", "analysis", "cb_qm_replay_round3_prereg_2026-10-24.md")
PRINTOUT = os.path.join(HERE, "03_round3.txt")
DRY_PRINTOUT = os.path.join(HERE, "03_round3_dryrun.txt")
STOPPED = os.path.join(HERE, "03_round3.STOPPED.txt")
OUT_DIR = f"{rp.B_DIR}/qm_streams/qm_round3_1024"
OUT_FILES = ("trades.tsv.gz", "adds.tsv", "g8_A.tsv", "g8_B.tsv", "g8_A_impact.txt", "g8_B_impact.txt", "account_his.tsv",
             "account_band.tsv")
# the first read's stored outputs (the parity gate reads them in the REAL run only) and the second read's (hashed only, never read)
FIRST = dict(ex.FIRST)
SECOND = {
    "second_trades": f"{ex.OUT_DIR}/trades.tsv.gz",
    "second_chains": f"{ex.OUT_DIR}/chains.tsv",
    "second_account_his": f"{ex.OUT_DIR}/account_his.tsv",
    "second_account_band": f"{ex.OUT_DIR}/account_band.tsv",
    "second_printout": ex.PRINTOUT,
}
FILES = {**ex.FILES, **SECOND}
CODE = {**ex.CODE,
        "round3_module": os.path.abspath(__file__),
        "round3_tests": os.path.join(HERE, "test_03_round3.py")}
# the second read's freeze record (docs/analysis/cb_qm_replay_execution_prereg_2026-10-23.md): its module, tests and doc body must be
# exactly the frozen ones; the first read's pins the second already carries
SECOND_MODULE_SHA = "346516fb4c236cc552103032163b790d030b10a536e83c70d4cf2390c3f9f485"
SECOND_TESTS_SHA = "6ce013bb1d7f1521e8083d014e4221fc837f30c59f9c5e00fbc023344d1a1949"
SECOND_DOC_BODY = "329ac865f814de0909332ff516ea5d52dea525fbef7b5fdcf1c9208a521143fe"
FIRST_DOC_BODY = ex.FIRST_DOC_BODY
PINNED = {**ex.PINNED, "exec_module": SECOND_MODULE_SHA, "exec_tests": SECOND_TESTS_SHA}
# the walk set IS the first read's: the minute trees this read opens must equal the first read's pins (its freeze record)
FIRST_MINUTES = {"A": "b6a99cdf084ad42c1a4d846e05d10b48404f8225499253583ff78170e95b592a",
                 "B": "d548f85679b9ded20bfa4650c45535d685d820d4dd2040fce84d01bae7b2b652"}

# ═════════════════════════════════════════════════════════════════════════════════════════════
# the registration's constants
# ═════════════════════════════════════════════════════════════════════════════════════════════
CUT_B = rp.CUT_B
HORIZON = rp.HORIZON
EXIT_SLIPS = rp.EXIT_SLIPS
SEED = rp.SEED
BAND_DRAWS = rp.BAND_DRAWS
BAND_KEY = ex.BAND_KEY                                   # the FIRST read's registered draws, reused (same seed, same key)
STRICT_BAND_KEY = ex.STRICT_BAND_KEY
FIRST_DIFF_KEY = ex.FIRST_DIFF_KEY                       # B0's date-matched difference = the first read's, same key
SPEED_CUT = cb.TRAIL_SPEED_ADR_CUT                       # W2: the 10-day when ADR20 at D is ABOVE it, else the 20-day (fixed 2026-10-18)
assert SPEED_CUT == 0.0479, SPEED_CUT
CAP30 = ex.CAP30                                         # the first read's `cap_30` row: 1% risk, 30% cap, 30% per stock, no margin
RISK_UP, RISK_OTHER = 0.01, 0.005                        # W3: QQQ at D "up" -> 1%; mixed / down / unknown -> 0.5%
MARGIN_GROSS = 2.0                                       # W4m: gross exposure up to 2x (borrow up to 1x the previous close's equity)
MIN_FILL_MINUTE = cb.OPENING_RANGE_MINUTES["orh5"]       # 5: an ORH5 fill is never in minute 0 (asserted on every walked fill)
BASELINE_FINAL_TXT = "2.044"                             # the first read's cap_30 row, as printed (asserted on the 3-decimal string)
BASELINE_YEARS_TXT = {2020: "62.8%", 2021: "26.2%"}
DEPTH_TOL = 1e-6                                         # base_low vs the stored base_depth: the runner's own cross-check tolerance
WIDTH_FLOOR_ADR = ex.WIDTH_FLOOR_ADR                     # 0.25: BESIDE only, the second read's R16 — a stop under 0.25 x ADR20 makes R a unit
assert WIDTH_FLOOR_ADR == 0.25                           # artifact (a base low just under the fill); the per-trade rows are re-read without them

STOPS = ("lod", "base_low", "lod_floor1")
BASE_ARM = rp.PRIMARY_ARM                                # p33_s3_t10
SPEED_ARM = "d3_p33_tspd"
ARMS = {BASE_ARM: cb.ARMS[BASE_ARM], "p33_s3_t20": cb.ARMS["p33_s3_t20"], "trail10_only": cb.ARMS["trail10_only"],
        SPEED_ARM: cb.HIS_EXIT_ARMS[SPEED_ARM]}
assert ARMS[SPEED_ARM].trail_mode == "speed" and ARMS[SPEED_ARM].partial_session == 3 and ARMS[SPEED_ARM].partial_trigger == "session"
assert ARMS["trail10_only"].partial_frac == 0.0 and ARMS["trail10_only"].trail_sma == 10


@dataclass(frozen=True)
class Variant:
    name: str
    label: str
    stop: str                 # a STOPS key
    arm: str                  # an ARMS key
    sizing: str               # "flat" (1% every trade) | "qqq" (W3) | "qqq_drop_down" (W3b: down-state trades not offered)
    gross_max: float = 1.0    # 1.0 = the first read's no-margin rule; 2.0 = W4m
    adds: bool = False        # W4a
    beside: bool = False


VARIANTS = (
    Variant("B0", "baseline: the first read's cap_30 row (ORH5, day low, too-wide skipped, p33_s3_t10)", "lod", BASE_ARM, "flat"),
    Variant("W1", "structural stop: the base low at D, no one-ADR skip, 1% risk", "base_low", BASE_ARM, "flat"),
    Variant("W1b", "the lower of the day low (through the minute before the fill) and one ADR below the fill (beside)", "lod_floor1",
            BASE_ARM, "flat", beside=True),
    Variant("W2", "hold winners longer: the 20-day trail, the 10-day when ADR20 at D > 4.79%", "lod", SPEED_ARM, "flat"),
    Variant("W2_t20", "the plain 20-day trail (beside; seen at the 20% cap)", "lod", "p33_s3_t20", "flat", beside=True),
    Variant("W2b", "no partial: the whole position trails on the 10-day (beside)", "lod", "trail10_only", "flat", beside=True),
    Variant("W3", "market-strength sizing: 1% when QQQ at D is up, 0.5% otherwise", "lod", BASE_ARM, "qqq"),
    Variant("W3b", "1% up, 0.5% mixed, no trade when QQQ is below both (beside)", "lod", BASE_ARM, "qqq_drop_down", beside=True),
    Variant("COMBINED", "W1 + W2 + W3 at the 30% cap", "base_low", SPEED_ARM, "qqq"),
    Variant("W4m_B0", "B0 with margin up to 2x gross (beside, B)", "lod", BASE_ARM, "flat", gross_max=MARGIN_GROSS, beside=True),
    Variant("W4m_C", "COMBINED with margin up to 2x gross (beside, B)", "base_low", SPEED_ARM, "qqq", gross_max=MARGIN_GROSS, beside=True),
    Variant("W4a_C", "COMBINED with one add on a new high after the day-3 partial (beside, B)", "base_low", SPEED_ARM, "qqq", adds=True,
            beside=True),
    Variant("W4ma_C", "COMBINED with margin and adds (beside, B)", "base_low", SPEED_ARM, "qqq", gross_max=MARGIN_GROSS, adds=True,
            beside=True),
)
VMAP = {v.name: v for v in VARIANTS}
FORK_VARIANT = "COMBINED"
# the variants with their OWN per-trade numbers: a distinct (stop, arm), or a distinct trade SET (W3b drops the down-state trades)
TRADE_VARIANTS = ("B0", "W1", "W1b", "W2", "W2_t20", "W2b", "W3b", "COMBINED")
SIZING_ONLY = {"W3": "B0", "W4m_B0": "B0", "W4m_C": "COMBINED", "W4a_C": "COMBINED", "W4ma_C": "COMBINED"}   # per-trade numbers = the source's
ADD_COMBOS = (("base_low", SPEED_ARM),)                  # the (stop, arm) sets adds are built for (the W4a variants' trade sets)
assert all((VMAP[s].stop, VMAP[s].arm) == (VMAP[v].stop, VMAP[v].arm) for v, s in SIZING_ONLY.items())
assert all((v.stop, v.arm) in ADD_COMBOS for v in VARIANTS if v.adds)

# the registration's §7 NEXT GAPS list, word for word (a test asserts it sits in the doc's §7 row)
NEXT_GAPS = "the EPs and parabolic shorts in his record; the trades he never mentioned on stream; adds / margin if still beside"
FORK_TEXT = {
    "EXPLAINED": "the structural stop, holding winners longer and market-strength sizing explain most of the shortfall: each one still has "
                 "to be validated on calls not used here (era B, the sealed 2025-26 table, new stream labels) before anything else is built "
                 "on it",
    "NEXT GAPS": "these three levers do not explain the shortfall on their own: the next gaps to test are " + NEXT_GAPS
                 + " (his rule, 10-23: a replay that does not reproduce his years is a defect in our implementation, never 'the setup does "
                 "not work')",
}


class GuardStop(Exception):
    pass


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the freeze lock — the second read's line-anchored lock, unchanged (the marker is matched ONLY as its own line, exactly once)
# ═════════════════════════════════════════════════════════════════════════════════════════════
FREEZE_MARKER = ex.FREEZE_MARKER
marker_spans = ex.marker_spans
doc_body_sha = ex.doc_body_sha
freeze_missing = ex.freeze_missing


def pins(minute_dates: "dict | None" = None, doc: "str | None" = None) -> dict:
    p = {name: rp.sha(path) for name, path in FILES.items()}
    p.update({name: rp.sha(path) for name, path in CODE.items()})
    p["first_doc_body"] = rp.doc_body_sha(rp.DOC)
    p["second_doc_body"] = ex.doc_body_sha(ex.DOC)
    for era, dates in (minute_dates or {}).items():
        p[f"minutes_{era}_used"] = rp.tree_sha(rp.minute_files_used(era, dates))
    p["doc_body"] = doc_body_sha(doc or DOC)
    return p


def existing_outputs() -> list:
    out = [p for p in (PRINTOUT, STOPPED) if os.path.exists(p)]
    out += [os.path.join(OUT_DIR, f) for f in OUT_FILES if os.path.exists(os.path.join(OUT_DIR, f))]
    return out


# ═════════════════════════════════════════════════════════════════════════════════════════════
# outcome-free facts: the base low at D (bars up to D), cross-checked against the stored base_depth
# ═════════════════════════════════════════════════════════════════════════════════════════════
POLE_COLS = rp.CAND_COLS + ("base_depth",)                 # base_depth = 1 - base_low / high(P), a D-night feature (not in FORBIDDEN)
assert not (rp.FORBIDDEN & set(POLE_COLS))


def load_poles() -> dict:
    """{(era, ticker, E): (pole_date, base_depth)} from the pinned candidate files, with the first read's own keep rules (era A: the tl
    rows; era B: discovery, D and E <= the cut, tl)."""
    out = {}
    for era, key, keep in (("A", "cand_A", rp.cand_keep_A), ("B", "cand_B", FIT.era_b_cand_keep)):
        df, _d = rp.read_tsv(rp.FILES[key], POLE_COLS, keep=keep)
        for tk, E, pd_, bd in zip(df["ticker"], df["E"], df["pole_date"], df["base_depth"]):
            out[(era, str(tk), str(E))] = (str(pd_), float(bd))
    return out


def base_low_facts(bars, cidx, cal, ev, pole_date: str, base_depth: float) -> tuple:
    """(base_low, P, implied_from_depth, D index) for one event, from bars up to D only: P = the pole bar (the candidate's pole_date,
    asserted a bar of this ticker before D), D = the bar before E, base_low = `runner.base_low_at` (the module's `explain_watch`
    formula, the lowest low over (P, D]); implied = high(P) x (1 - base_depth), the candidate's own number for the same quantity."""
    e = R.locate_breakout_index(cal, cidx, ev.E)
    i = e - 1
    if not (i >= 0 and bars.dates[i].isoformat() == ev.D):
        raise ValueError(f"{ev.ticker} {ev.E}: D {ev.D} is not the bar before E")
    P = bisect.bisect_left(bars.dates, date.fromisoformat(pole_date))
    if not (P < i and bars.dates[P].isoformat() == pole_date):
        raise ValueError(f"{ev.ticker} {ev.E}: pole_date {pole_date} is not a bar before D")
    bl = R.base_low_at(bars, P, i)
    implied = float(bars.h[P]) * (1.0 - float(base_depth))
    return bl, P, implied, i


def prepare(S: dict, poles: dict) -> dict:
    """The walk set (every kept event of the first read: his / control / post-E-only — no re-entry rows, nothing chains here) with the
    base low at D per event, the base_depth cross-check counted (never silently passed), and the outcome-free facts. -> dict."""
    walk = {(x.era, x.ticker, x.E): x for x in S["evs"] if x.keep}
    base_low, pole_idx, bad, facts = {}, {}, [], Counter()
    cache = {}
    for k, ev in walk.items():
        D = S["Ds"][ev.era]
        if (ev.era, ev.ticker) not in cache:
            cache[(ev.era, ev.ticker)] = R.bars_for(D, D.tid[ev.ticker])
        bars, cidx = cache[(ev.era, ev.ticker)]
        if k not in poles:
            raise KeyError(f"{k}: no candidate row for its pole")
        pd_, bd = poles[k]
        bl, P, implied, _i = base_low_facts(bars, cidx, D.cal, ev, pd_, bd)
        base_low[k], pole_idx[k] = bl, P
        facts[f"{ev.era}_events"] += 1
        if abs(implied - bl) > DEPTH_TOL * max(1.0, bl):
            bad.append((k, bl, implied))
    facts["depth_mismatch"] = len(bad)
    return dict(walk=walk, base_low=base_low, pole_idx=pole_idx, depth_bad=bad, facts=facts)


def width_adr_at_level(ev, base_low: float) -> float:
    """The width of a stop at the base low measured from the LEVEL (pivot at D), in ADR20 units — outcome-free (pivot, base low and
    ADR20 are all at D). Negative when the base low sits above the level."""
    return (ev.pivot - base_low) / (ev.pivot * ev.adr20)


def describe_round3(say, S: dict, X: dict) -> None:
    say("\n## The base low at D (outcome-free: daily bars up to D; the module's `explain_watch` formula, lowest low over (P, D])")
    say(f"- cross-check against the candidate's stored base_depth (= 1 - base_low / high(P), tolerance {DEPTH_TOL:g} relative): "
        f"mismatches {X['facts']['depth_mismatch']} of {X['facts']['A_events'] + X['facts']['B_events']:,} events"
        + ("" if not X["depth_bad"] else " — FIRST: " + "; ".join(f"{k} base_low {bl:.4f} implied {im:.4f}" for k, bl, im in X["depth_bad"][:5])))
    for e in ("A", "B"):
        for nm in ("his", "ctl", "post"):
            evs = [x for k, x in X["walk"].items() if x.era == e and getattr(x, nm)]
            if not evs:
                continue
            w = np.array([width_adr_at_level(x, X["base_low"][(x.era, x.ticker, x.E)]) for x in evs])
            above = int((w <= 0).sum())
            near = int((w < WIDTH_FLOOR_ADR).sum())
            say(f"- era {e} {nm} (n = {len(evs):,}): a stop at the base low, measured from the LEVEL, in ADR20 units: median {np.median(w):.2f}, "
                f"90th pct {np.percentile(w, 90):.2f}; wider than 1 / 2 / 3 ADR: {100 * (w > 1).mean():.1f}% / {100 * (w > 2).mean():.1f}% / "
                f"{100 * (w > 3).mean():.1f}%; base low AT OR ABOVE the level {above} (under W1 such an event abstains when its base low is "
                f"at or above the FILL, else fills with a stop under 0.1% wide); within {WIDTH_FLOOR_ADR:g} ADR under the level or above it "
                f"{near} (only among these can a W1 stop be under {WIDTH_FLOOR_ADR:g} ADR from the fill: the near-zero-stop re-read, §5)")
    say("\n## W2's speed cut and W3's market state (outcome-free: ADR20 and QQQ at D)")
    for e in ("A", "B"):
        for nm in ("his", "ctl"):
            evs = [x for k, x in X["walk"].items() if x.era == e and getattr(x, nm)]
            if not evs:
                continue
            fast = sum(1 for x in evs if x.adr20 > SPEED_CUT)
            q = Counter(x.qqq for x in evs)
            say(f"- era {e} {nm} (n = {len(evs):,}): ADR20 at D above {100 * SPEED_CUT:.2f}% (W2 trails the 10-day) {fast} "
                f"({100 * fast / len(evs):.1f}%), else the 20-day {len(evs) - fast}; QQQ at D: up {q['up']} (W3 risk 1%), mixed {q['mixed']} "
                f"(0.5%), down {q['down']} (0.5%; W3b: no trade), unknown {q['']} (0.5%)")


# ═════════════════════════════════════════════════════════════════════════════════════════════
# THE WALK (real run only): the stop sets
# ═════════════════════════════════════════════════════════════════════════════════════════════
def has_fill(en: dict) -> bool:
    """A module row that carries a fill: a fill, or a `too_wide` abstain (it keeps fill / stop / fill_minute / level)."""
    return en["status"] == "filled" or (en["status"] == "abstain" and en["reason"] == "too_wide")


def with_stop(en: dict, stop: float, mb) -> dict:
    """The module's ORH5 row (a fill or a too-wide abstain) re-stopped at `stop`: a fresh row with the module's own `day0_walk` on
    the new stop, NO one-ADR skip (W1 / W1b are wider than one ADR by construction or by design). A stop at or above the fill abstains
    `stop_at_or_above_fill` (the module's own name), counted by the caller."""
    assert has_fill(en), en["status"]
    fill = float(en["fill"])
    stop = float(stop)
    if stop >= fill:
        return {"status": "abstain", "reason": "stop_at_or_above_fill", "fill": fill, "stop": stop, "fill_minute": en["fill_minute"],
                "width_pct": None, "level": en["level"], "day0": None}
    return {"status": "filled", "reason": None, "fill": fill, "stop": stop, "fill_minute": en["fill_minute"],
            "width_pct": (fill - stop) / fill, "level": en["level"],
            "day0": cb.day0_walk(mb, fill_minute=en["fill_minute"], stop=stop)}


def lod_prior(mb, fill_minute: int) -> float:
    """The low of the day through the minute BEFORE the fill minute (never the fill minute's own low — the second read's §1.4b
    trap). ORH5 fills at minute 5 or later, after at least one opening-range bar, so the range is never empty (asserted)."""
    m = int(np.searchsorted(mb.minute, fill_minute))
    assert m < len(mb.minute) and int(mb.minute[m]) == int(fill_minute), (fill_minute, m)
    assert m >= 1, "a fill on the day's first bar has no prior low (ORH5 cannot fill there)"
    return float(mb.l[:m].min())


def stop_set_entries(en: dict, mb, base_low: float, adr20: float) -> dict:
    """{stop set: entry row} for one event's ORH5 row: `lod` = the module's row unchanged (a too-wide abstain stays one: the
    registered rule); `base_low` = W1; `lod_floor1` = W1b, min(lod_prior, fill x (1 - ADR20)). A row with no fill is the same abstain
    under every set (there is nothing to re-stop)."""
    if not has_fill(en):
        return {s: en for s in STOPS}
    fill = float(en["fill"])
    return {"lod": en,
            "base_low": with_stop(en, base_low, mb),
            "lod_floor1": with_stop(en, min(lod_prior(mb, en["fill_minute"]), fill * (1.0 - adr20)), mb)}


def walk_event3(ev, bars, cidx, e: int, mb, breaks: "np.ndarray | None", base_low: float) -> dict:
    """{"sets": {stop: {"entry", "arms": {arm: raw}}}, n_fwd, hole, break_cut, own_low} for ONE event, wired exactly as the first read's
    `walk_event` (E alignment, the 130-session contiguity, closes_before through E, `forward_window`, the cut at an identity break after
    E). The ORH5 row comes from `cb.entry_variants` once; every stop set walks every arm of `ARMS` through `cb.walk_arms`, which books a
    day-0 stop-out once for every arm. `own_low` (print-only, the second read's flag) marks a fill whose stop is its own minute's low."""
    assert bars.dates[e].isoformat() == ev.E, (ev.ticker, e, ev.E)
    assert e >= cb.MIN_HISTORY and int(cidx[e]) - int(cidx[e - cb.MIN_HISTORY]) == cb.MIN_HISTORY, (ev.ticker, ev.E)
    en = cb.entry_variants(mb, pivot=ev.pivot, adr20=ev.adr20, day_high=float(bars.h[e]), day_low=float(bars.l[e]))[rp.ENTRY]
    if has_fill(en):
        assert int(en["fill_minute"]) >= MIN_FILL_MINUTE, (ev.ticker, ev.E, en["fill_minute"])   # never a minute-0 fill, in any variant
    own = ex.own_low_flag(mb, en) if has_fill(en) else None
    closes_before = bars.c[:e + 1]
    assert float(closes_before[-1]) == float(bars.c[e])
    fwd, cut = cb.forward_window(bars, cidx, e, HORIZON)
    fwd, brk = rp.cut_at_break(fwd, bars.dates[e], breaks)
    out = {"n_fwd": len(fwd), "hole": bool(cut), "break_cut": brk, "own_low": own, "sets": {}}
    for s, en_s in stop_set_entries(en, mb, base_low, ev.adr20).items():
        raws = {}
        if en_s["status"] == "filled":
            raws = cb.walk_arms(en_s, closes_before=closes_before, fwd=fwd, adr20=ev.adr20, horizon=HORIZON, arms=ARMS)
        out["sets"][s] = {"entry": en_s, "arms": raws}
    return out


def walk_all3(S: dict, X: dict) -> tuple:
    """Walk every event of the walk set once. -> (results, tally)."""
    res, tally = {}, Counter()
    for e in ("A", "B"):
        D = S["Ds"][e]
        by_date = defaultdict(list)
        for k, ev in X["walk"].items():
            if ev.era == e:
                by_date[ev.E].append(ev)
        cache = {}
        for di, (d, evs) in enumerate(sorted(by_date.items())):
            path = S["files"][e].get(d)
            if path is None:
                blocks, info = {}, {"truncated": False}
                tally[f"{e}_minute_date_file_absent"] += 1
            else:
                blocks, info = R.read_minute_file(path, want={x.ticker for x in evs})
            tally[f"{e}_minute_truncated"] += int(info["truncated"])
            done = {(d, x.ticker): x.minutes_state for x in evs}
            for ev in evs:
                mb, state = R.minutes_for(blocks, done, d, ev.ticker)
                tally[f"{e}_minutes_{state}"] += 1
                if ev.ticker not in cache:
                    cache[ev.ticker] = R.bars_for(D, D.tid[ev.ticker])
                bars, cidx = cache[ev.ticker]
                eidx = R.locate_breakout_index(D.cal, cidx, ev.E)
                k = (e, ev.ticker, ev.E)
                w = walk_event3(ev, bars, cidx, eidx, mb, breaks=S["guards"][e].get(ev.ticker), base_low=X["base_low"][k])
                if w["break_cut"]:
                    tally[f"{e}_forward_window_cut_at_a_break"] += 1
                w["bars"], w["cidx"], w["e"] = bars, cidx, eidx
                res[k] = w
            if (di + 1) % 100 == 0:
                print(f"  era {e}: {di + 1}/{len(by_date)} dates walked", flush=True)
    return res, tally


def trades_for_combo(X: dict, res: dict, stop: str, arm: str) -> dict:
    """{(era, ticker, E): Trade} for every FILLED walk under one (stop set, arm) (the first read's `make_trade`, unchanged)."""
    out = {}
    for k, w in res.items():
        s = w["sets"][stop]
        if arm not in s["arms"]:
            continue
        out[k] = rp.make_trade(X["walk"][k], s["entry"], s["arms"][arm], w["bars"], w["cidx"], w["e"], w["n_fwd"])
    return out


# ═════════════════════════════════════════════════════════════════════════════════════════════
# sizing (W3) and the account with two switches (per-trade risk, margin) — the first read's `simulate`, line for line otherwise
# ═════════════════════════════════════════════════════════════════════════════════════════════
def risk_qqq(qqq_of: dict):
    """W3: 1% when QQQ at the trade's D is "up" (above both its 10- and 20-day averages), 0.5% otherwise (mixed / down / unknown)."""
    def risk_of(t) -> float:
        return RISK_UP if qqq_of.get(t.key) == "up" else RISK_OTHER
    return risk_of


def drop_down(trades: list, qqq_of: dict) -> tuple:
    """W3b: the trades whose QQQ at D is below both averages are not offered. -> (kept, n dropped)."""
    kept = [t for t in trades if qqq_of.get(t.key) != "down"]
    return kept, len(trades) - len(kept)


def simulate3(trades: list, cfg: "rp.Config", cal: list, start_ci: int, risk_of=None, gross_max: float = 1.0) -> dict:
    """The first read's `simulate` (01_replay.py l.772-883), line for line, with two switches that are OFF at their defaults:
      risk_of(t) -> the fraction of the previous close's equity this trade risks (None = cfg.risk on every trade, the first read's);
      gross_max  -> the room a trade may take = the free cash + (gross_max - 1) x the previous close's equity. At 1.0 that is the free
                    cash exactly (the first read's no-margin rule: the same comparison, the same arithmetic); at 2.0 (W4m) a trade may
                    borrow up to one times the equity, so positions at cost may reach twice the equity; no interest is charged.
    Extra counts: `risk_<r>` entries per risk level, `min_cash` (the deepest borrowing, <= 0 only with margin). Parity with `rp.simulate`
    at the defaults is asserted in the real run on the baseline and tested on random trade lists."""
    acts = []
    for k, t in enumerate(trades):
        acts.append((t.e_ci, rp.ORDER_BUY, t.fill_minute, t.ticker, 0, k))
        for li, lg in enumerate(t.legs):
            acts.append((lg[0], lg[1], 0, "", li + 1, k))
    acts.sort()
    end_ci = max([a[0] for a in acts], default=start_ci)
    cash = 1.0
    shares0, rem = {}, {}
    held = Counter()
    cost_held = defaultdict(float)
    counts = Counter()
    entered_by_year, skipped_by_year = Counter(), Counter()
    eq_prev = 1.0
    curve_ci, curve_eq = [], []
    max_open, max_gross, min_cash = 0, 0.0, 1.0
    p, n_act = 0, len(acts)
    for ci in range(start_ci, end_ci + 1):
        while p < n_act and acts[p][0] == ci:
            _ci, order, _fm, _tk, seq, k = acts[p]
            t = trades[k]
            if order == rp.ORDER_BUY:
                y = cal[ci].year
                if cfg.same_ticker == "skip" and held[t.ticker] > 0:
                    counts["skipped_same_ticker"] += 1
                    skipped_by_year[y] += 1
                else:
                    r = cfg.risk if risk_of is None else float(risk_of(t))
                    value = eq_prev * min(r / t.width, cfg.cap)
                    stock_trim = False
                    if cfg.stock_limit is not None:
                        room_stock = cfg.stock_limit * eq_prev - cost_held[t.ticker]
                        if room_stock <= 1e-12:
                            counts["skipped_stock_limit"] += 1
                            skipped_by_year[y] += 1
                            value = 0.0
                        elif value > room_stock + 1e-12:
                            value = room_stock
                            stock_trim = True
                    room = cash + (gross_max - 1.0) * eq_prev
                    if value > 0 and value > room + 1e-12:
                        if cfg.room == "trim" and room > 1e-12:
                            value = room
                            counts["trimmed"] += 1
                        else:
                            counts["skipped_no_room"] += 1
                            skipped_by_year[y] += 1
                            value = 0.0
                    if value > 0:
                        if held[t.ticker] > 0:
                            counts["same_ticker_concurrent"] += 1
                        if min(r / t.width, cfg.cap) == cfg.cap:
                            counts["cap_bound"] += 1
                        if stock_trim:
                            counts["stock_limit_trimmed"] += 1
                        sh = value / t.fill
                        shares0[k] = sh
                        rem[k] = sh
                        held[t.ticker] += 1
                        cost_held[t.ticker] += value
                        cash -= value
                        counts["entered"] += 1
                        counts[f"risk_{r:g}"] += 1
                        entered_by_year[y] += 1
                        max_open = max(max_open, len(rem))
                        min_cash = min(min_cash, cash)
            elif k in rem:
                _lci, _o, frac, px, _kind, _s = t.legs[seq - 1]
                sh = shares0[k] * frac
                cash += sh * px * (1.0 - cfg.exit_slip)
                rem[k] -= sh
                cost_held[t.ticker] -= sh * t.fill
                if rem[k] <= shares0[k] * 1e-9:
                    del rem[k]
                    held[t.ticker] -= 1
                    if held[t.ticker] == 0:
                        cost_held[t.ticker] = 0.0
            p += 1
        pos_val = 0.0
        for k, sh in rem.items():
            t = trades[k]
            pos_val += sh * float(t.path_c[ci - t.e_ci])
        eq = cash + pos_val
        if eq > 0:
            max_gross = max(max_gross, pos_val / eq)
        curve_ci.append(ci)
        curve_eq.append(eq)
        eq_prev = eq
    assert not rem, f"{len(rem)} positions still open after the last leg"
    eqa = np.asarray(curve_eq, dtype=float)
    peak = np.maximum.accumulate(np.concatenate(([1.0], eqa)))[1:] if len(eqa) else eqa
    dd = float((1.0 - eqa / peak).max()) if len(eqa) else 0.0
    year_end, prev, yearly = {}, 1.0, {}
    for ci, eq in zip(curve_ci, curve_eq):
        year_end[cal[ci].year] = eq
    for y in sorted(year_end):
        yearly[y] = year_end[y] / prev - 1.0
        prev = year_end[y]
    return {"final": float(eqa[-1]) if len(eqa) else 1.0, "year_end": year_end, "yearly": yearly, "max_dd": dd, "counts": counts,
            "entered_by_year": entered_by_year, "skipped_by_year": skipped_by_year, "max_open": max_open, "max_gross": max_gross,
            "min_cash": min_cash, "curve": (curve_ci, curve_eq)}


def curves_equal(a: dict, b: dict) -> bool:
    """The first read's `simulate` result `a` equals `simulate3`'s `b`: the same days, the same equity on every day (bit for bit), the
    same counts (simulate3's extra `risk_<r>` keys aside), the same final / drawdown / max open / max gross."""
    ca, cb_ = a["curve"], b["curve"]
    if list(ca[0]) != list(cb_[0]) or len(ca[1]) != len(cb_[1]) or any(x != y for x, y in zip(ca[1], cb_[1])):
        return False
    kb = Counter({k: v for k, v in b["counts"].items() if not k.startswith("risk_")})
    return (Counter(a["counts"]) == kb and a["final"] == b["final"] and a["max_dd"] == b["max_dd"] and a["max_open"] == b["max_open"]
            and a["max_gross"] == b["max_gross"] and a["yearly"] == b["yearly"])


# ═════════════════════════════════════════════════════════════════════════════════════════════
# W4a — one add per trade on a new high after the day-3 partial (BESIDE, B)
# ═════════════════════════════════════════════════════════════════════════════════════════════
def add_for(t: "rp.Trade", bars, e: int, cidx, cal: list, qqq: tuple) -> tuple:
    """(add Trade or None, reason). The add exists when the walk took the SESSION-3 partial and the remainder exited on session s_exit >=
    5: on the first session j in 4 .. s_exit - 1 whose HIGH exceeds the highest high over sessions 0 .. j - 1 (E's own high included),
    the add fills at that prior high — or at the open when the session opened above it — plus the entry slippage; its stop is the
    position's stop in force after the partial (the fill, i.e. breakeven); it exits with the remainder at the remainder's final leg
    (its price, date and order). A stop day never adds (the walk booked the stop first: j < s_exit). Its QQQ state is read at the
    session before the add (W3 sizing). An add whose stop is at or above its fill is skipped (counted). Reasons: no_partial, no_room,
    no_new_high, stop_at_or_above_fill, ok."""
    legs = t.legs
    if not any(lg[4] == "partial" and lg[5] == 3 for lg in legs):
        return None, "no_partial"
    final = max(legs, key=lambda lg: lg[5])
    s_exit = int(final[5])
    if s_exit < 5:
        return None, "no_room"
    j_add, level = None, None
    for j in range(4, s_exit):
        prior = float(bars.h[e:e + j].max())
        if float(bars.h[e + j]) > prior:
            j_add, level = j, prior
            break
    if j_add is None:
        return None, "no_new_high"
    op = float(bars.o[e + j_add])
    gap = op > level
    fill = (op if gap else level) * (1.0 + cb.ENTRY_SLIPPAGE_PCT)
    stop = float(t.fill)
    if stop >= fill:
        return None, "stop_at_or_above_fill"
    held = s_exit - j_add
    px = float(final[3])
    rs = tuple((px * (1.0 - s) - fill) / (fill - stop) for s in EXIT_SLIPS)
    e_ci = int(cidx[e + j_add])
    qb, qc = qqq
    d_ci = e_ci - 1
    p = int(np.searchsorted(qc, d_ci))
    state = rp.qqq_state_at(qb.c, p) if (p < len(qc) and int(qc[p]) == d_ci) else ""
    add = rp.Trade(key=(t.era, t.ticker, f"{t.key[2]}|add{j_add}"), ticker=t.ticker, era=t.era, e_ci=e_ci,
                   fill_minute=0 if gap else 389, fill=fill, stop=stop, width=(fill - stop) / fill, status=t.status, mature=t.mature,
                   realized_r=rs[0], r_slip=rs, sessions_held=held, legs=[(int(final[0]), int(final[1]), 1.0, px, final[4], held)],
                   path_c=np.asarray(bars.c[e + j_add:e + s_exit + 1], dtype=float), retrigger=t.retrigger, year=cal[e_ci].year,
                   month=cal[e_ci].isoformat()[:7])
    return add, ("ok", state)


def adds_for_combo(T: dict, res: dict, S: dict) -> tuple:
    """{origin key: add Trade} over every trade of one (stop, arm) set, plus {add key: qqq state} and the reasons Counter."""
    adds, states, reasons = {}, {}, Counter()
    for k, t in T.items():
        w = res[k]
        a, why = add_for(t, w["bars"], w["e"], w["cidx"], S["Ds"][t.era].cal, S["qqq"][t.era])
        if a is None:
            reasons[why] += 1
            continue
        reasons["ok"] += 1
        adds[k] = a
        states[a.key] = why[1]
    return adds, states, reasons


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the trade list of a variant for a set of events (his calls, or one band draw)
# ═════════════════════════════════════════════════════════════════════════════════════════════
def variant_trades(v: Variant, keys, T: dict, adds: dict, qqq_of: dict) -> tuple:
    """The account's trade list for `keys` under variant `v`: each event's trade (if filled), W3b's down-state drop, W4a's adds (an add
    enters right after its origin in the list; the account orders by date anyway). -> (trades, n dropped)."""
    tr = [T[k] for k in keys if k in T]
    dropped = 0
    if v.sizing == "qqq_drop_down":
        tr, dropped = drop_down(tr, qqq_of)
    if v.adds:
        out = []
        for t in tr:
            out.append(t)
            a = adds.get(t.key)
            if a is not None:
                out.append(a)
        tr = out
    return tr, dropped


def risk_fn(v: Variant, qqq_of: dict):
    return None if v.sizing == "flat" else risk_qqq(qqq_of)


# ═════════════════════════════════════════════════════════════════════════════════════════════
# measures
# ═════════════════════════════════════════════════════════════════════════════════════════════
def width_adr_line(trades: list, X: dict) -> str:
    w = np.array([t.width / X["walk"][t.key].adr20 for t in trades if t.key in X["walk"]])
    if not len(w):
        return "-"
    return f"median {np.median(w):.2f}, 90th pct {np.percentile(w, 90):.2f}, under 1 ADR {100 * (w <= 1).mean():.0f}%"


def date_matched3(his_ev: list, ctl_ev: list, T: dict, key: str, drop_down_states: bool = False, qqq_of: "dict | None" = None,
                  keep=None) -> dict:
    """His minus control, DATE-MATCHED (the first read's `paired_block_diff`, unchanged; the first read's `his_minus_control` shape): per
    filled MATURE trade, in the cell (date of E, first break / retrigger); weights = his filled mature trades' stratum shares; month
    blocks, 2,000 resamples, seed 702. Mean R and >= 10R per 100. `drop_down_states` removes the QQQ-down trades from BOTH arms (W3b);
    `keep(t)` is a further filter on both arms (the near-zero-stop re-read, beside)."""
    def pick(evs):
        tr = [T[(x.era, x.ticker, x.E)] for x in evs if (x.era, x.ticker, x.E) in T and T[(x.era, x.ticker, x.E)].mature]
        if drop_down_states:
            tr = [t for t in tr if qqq_of.get(t.key) != "down"]
        if keep is not None:
            tr = [t for t in tr if keep(t)]
        return tr
    his_t, ctl_t = pick(his_ev), pick(ctl_ev)
    nf = Counter(t.retrigger for t in his_t)
    w = {s: nf[s] / len(his_t) for s in (0, 1)} if his_t else {0: 0.5, 1: 0.5}
    out = {"_n": (len(his_t), len(ctl_t))}
    for meas, f in (("mean R", lambda r: r), (">=10R /100", lambda r: rp.PER * (r >= 10.0))):
        k = key if meas == "mean R" else key.replace("|mean R", "") + f"|{meas}"
        out[meas] = rp.paired_block_diff(
            f(np.array([t.realized_r for t in his_t], dtype=float)), [t.month for t in his_t], [t.retrigger for t in his_t],
            f(np.array([t.realized_r for t in ctl_t], dtype=float)), [t.month for t in ctl_t], [t.retrigger for t in ctl_t], w,
            a_date=[t.key[2] for t in his_t], b_date=[t.key[2] for t in ctl_t], key=k)
    return out


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the baseline-parity gate (real run): B0 must BE the first read's cap_30 row
# ═════════════════════════════════════════════════════════════════════════════════════════════
PARITY_ARMS = (BASE_ARM, "p33_s3_t20")                  # both exist in the first read's trade table: the exit walker is checked on both


def parity_trades3(first_trades_path: str, orig_keys: set, res: dict, TT: dict) -> list:
    """B0's ORH5 entries and its p33_s3_t10 AND p33_s3_t20 walks against the first read's `trades.tsv.gz` (10 significant digits): the
    same event set, every entry status / reason, and for every fill the fill, stop, fill minute, status, maturity, sessions held and R.
    -> list of mismatch strings (empty = parity)."""
    t = pd.read_csv(first_trades_path, sep="\t", dtype=str, keep_default_na=False)
    t = t[(t["variant"] == rp.ENTRY) & (t["arm"].isin(PARITY_ARMS) | (t["entry_status"] != "filled"))]
    bad = []
    keys = set(zip(t["era"], t["ticker"], t["E"]))
    if keys != orig_keys:
        bad.append(f"event set differs: first read {len(keys)}, B0 {len(orig_keys)}, only-first {len(keys - orig_keys)}, "
                   f"only-B0 {len(orig_keys - keys)}")
    n_checked = Counter()
    for r in t.itertuples(index=False):
        k = (r.era, r.ticker, r.E)
        if k not in res:
            continue
        en = res[k]["sets"]["lod"]["entry"]
        if en["status"] != r.entry_status or (en["reason"] or "") != r.entry_reason:
            bad.append(f"{k}: entry {en['status']}:{en['reason']} vs {r.entry_status}:{r.entry_reason}")
            continue
        if r.entry_status != "filled":
            continue
        tr = TT[("lod", r.arm)].get(k)
        if tr is None:
            bad.append(f"{k} {r.arm}: filled in the first read, no B0 trade")
            continue
        n_checked[r.arm] += 1
        for nm, mine, theirs in (("fill", tr.fill, float(r.fill)), ("stop", tr.stop, float(r.stop)),
                                 ("realized_r", tr.realized_r, float(r.realized_r))):
            if not ex._close(mine, theirs):
                bad.append(f"{k} {r.arm}: {nm} {mine!r} vs {theirs!r}")
        if (tr.fill_minute != int(r.fill_minute) or tr.status != r.status or int(tr.mature) != int(r.mature)
                or tr.sessions_held != int(r.sessions_held)):
            bad.append(f"{k} {r.arm}: fill minute / status / mature / held {tr.fill_minute}/{tr.status}/{int(tr.mature)}/{tr.sessions_held} "
                       f"vs {r.fill_minute}/{r.status}/{r.mature}/{r.sessions_held}")
    if any(n_checked[a] == 0 for a in PARITY_ARMS) and orig_keys:
        bad.append(f"no first-read fill checked on an arm: {dict(n_checked)}")
    return bad


# ═════════════════════════════════════════════════════════════════════════════════════════════
# main
# ═════════════════════════════════════════════════════════════════════════════════════════════
def main(argv=None) -> int:
    ap_ = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap_.add_argument("--dry-run", action="store_true", help="load + populations + the base low at D + coverage + pins; no outcome")
    args = ap_.parse_args(argv)
    dry = args.dry_run
    say = rp.Say()
    if not dry:
        ex_ = existing_outputs()
        if ex_:
            print(f"REFUSED: output(s) already on disk: {ex_} (this read runs once; after a STOPPED run, recovery = the fix, then delete "
                  f"the STOPPED file AND every file under {OUT_DIR} by hand, re-freeze if the module changed)", file=sys.stderr)
            return 2
    t0 = time.time()
    say(f"# #705 QM replay — 03_round3 ({'DRY RUN: no minute file opened, no entry / exit function called, no outcome file read, no outcome computed' if dry else 'THE REGISTERED READ'})")
    say(f"# registration: {os.path.relpath(DOC, REPO)}")
    p0 = {k: rp.sha(v) for k, v in {**FILES, **CODE}.items() if k in PINNED and os.path.exists(v)}
    drift = [f"{k}: {p0.get(k)} (pinned {v})" for k, v in PINNED.items() if p0.get(k) != v]
    fdb = rp.doc_body_sha(rp.DOC) if os.path.exists(rp.DOC) else ""
    if fdb != FIRST_DOC_BODY:
        drift.append(f"first_doc_body: {fdb} (frozen {FIRST_DOC_BODY})")
    sdb = ex.doc_body_sha(ex.DOC) if os.path.exists(ex.DOC) else ""
    if sdb != SECOND_DOC_BODY:
        drift.append(f"second_doc_body: {sdb} (frozen {SECOND_DOC_BODY})")
    missing = [k for k, v in {**FIRST, **SECOND}.items() if not os.path.exists(v)]
    if drift or missing:
        say("REFUSED: " + ("a pinned input changed: " + "; ".join(drift) if drift else "")
            + (f" the earlier reads' outputs are missing: {missing}" if missing else ""))
        say.write(DRY_PRINTOUT if dry else STOPPED)
        return 2
    say("- pins re-checked: the Track A inputs, the cb module, the frozen first replay (module c4478588…, tests 37c918a0…, doc body "
        "aaaadd29…), the frozen second read (module 346516fb…, tests 6ce013bb…, doc body 329ac865…): no drift; both reads' outputs are "
        "on disk (hashed below, not parsed)")
    say("\n## Loads (the first read's loader; era B: every row dated after 2024-12-31 dropped at read)")
    S = rp.load_all(say, dry)
    rp.describe_population(say, S)
    poles = load_poles()
    X = prepare(S, poles)
    describe_round3(say, S, X)
    if X["facts"]["depth_mismatch"]:
        raise AssertionError(f"BASE LOW CROSS-CHECK FAILED on {X['facts']['depth_mismatch']} events: the pole or the base window is wrong")
    say("- the base low reproduces the candidate's stored base_depth on every event (asserted)")
    mdates = {e: sorted({x.E for x in X["walk"].values() if x.era == e}) for e in ("A", "B")}
    p = pins(mdates)
    bad_min = [e for e in ("A", "B") if p[f"minutes_{e}_used"] != FIRST_MINUTES[e]]
    if bad_min:
        say(f"REFUSED: the minute trees this read opens differ from the first read's pins on era {bad_min}: the walk set is not the first read's")
        say.write(DRY_PRINTOUT if dry else STOPPED)
        return 2
    say(f"- the minute date files the walk set opens (era A {len(mdates['A'])}, era B {len(mdates['B'])}) hash to the first read's pins: "
        "the walk set is the first read's")
    say("\n## Pins (sha256) — every value below goes under the doc's freeze marker line before the real run")
    for k, v in p.items():
        what = FILES.get(k) or CODE.get(k) or {"first_doc_body": "the first registration's text above its marker (frozen)",
                                               "second_doc_body": "the second registration's text above its marker line (frozen)",
                                               "doc_body": "this registration's text above its marker line"}.get(k) \
            or f"the {len(mdates[k[8]])} minute date files the walk set opens"
        say(f"- {k}: {v}  {what}")
    miss = freeze_missing(DOC, p)
    say(f"- freeze record: {'every pin above is written under the freeze marker line' if not miss else 'NOT YET under the freeze marker line: ' + ', '.join(miss)}")
    if dry:
        say(f"\n## DRY RUN ends here: no minute file opened, no entry / exit / R / return computed, no outcome file read. ({time.time() - t0:.0f}s)")
        say.write(DRY_PRINTOUT)
        return 0
    if miss:
        say("REFUSED: the real read runs only after the freeze commit records every pin above under the marker line.")
        print("\n".join(say.lines[-2:]), file=sys.stderr)
        return 2
    try:
        run_round3(S, X, say)
    except GuardStop as g:
        say(f"\nSTOPPED: {g} ({time.time() - t0:.0f}s)")
        say.write(STOPPED)
        return 3
    except Exception:
        import traceback
        say("\nCRASHED:\n" + traceback.format_exc())
        say.write(STOPPED)
        return 3
    say(f"\n({time.time() - t0:.0f}s)")
    say.write(PRINTOUT)
    return 0


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the real run (after the freeze only)
# ═════════════════════════════════════════════════════════════════════════════════════════════
def run_round3(S: dict, X: dict, say) -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    res, tally = walk_all3(S, X)
    TT = {(s, a): trades_for_combo(X, res, s, a) for s in STOPS for a in ARMS}
    groups = {}
    for e in ("A", "B"):
        evs = [x for x in X["walk"].values() if x.era == e]
        groups[e] = {"his": [x for x in evs if x.his], "ctl": [x for x in evs if x.ctl], "post": [x for x in evs if x.post]}
    GA = groups["A"]
    calA = S["Ds"]["A"].cal
    startA = bisect.bisect_left(calA, date.fromisoformat(min(x.E for x in GA["his"] + GA["ctl"])))
    orig_keys = set(X["walk"])
    qqq_of = {k: x.qqq for k, x in X["walk"].items()}
    adds, add_reasons = {}, {}
    for combo in ADD_COMBOS:
        adds[combo], st, add_reasons[combo] = adds_for_combo(TT[combo], res, S)
        qqq_of.update(st)
    keys_his = [(x.era, x.ticker, x.E) for x in GA["his"]]

    # ---- G8 on the union of every trade of this read (every stop x exit, adds included), BEFORE any number
    g8 = {}
    for e in ("A", "B"):
        rows, seen = [], set()
        cal = S["Ds"][e].cal
        for combo in TT:
            for k, t in sorted(TT[combo].items()):
                if k[0] == e and (k[1], k[2], t.sessions_held) not in seen:
                    seen.add((k[1], k[2], t.sessions_held))
                    rows.append((BASE_ARM, k[1], k[2], t.sessions_held, t.realized_r))
        for combo in adds:
            for k, a in sorted(adds[combo].items()):
                if k[0] == e:
                    d = cal[a.e_ci].isoformat()
                    if (a.ticker, d, a.sessions_held) not in seen:
                        seen.add((a.ticker, d, a.sessions_held))
                        rows.append((BASE_ARM, a.ticker, d, a.sessions_held, a.realized_r))
        path = os.path.join(OUT_DIR, f"g8_{e}.tsv")
        rp.write_g8_file(path, rows)
        g8[e] = rp.run_g8(e, path, os.path.join(OUT_DIR, f"g8_{e}_impact.txt"))
    if g8["A"] != (0, 0):
        raise GuardStop(f"G8 era A {g8['A']} != (0, 0): the read does not quote a number")

    # ---- accounts and bands (computed before printing; the parity gate reads B0)
    his_by_date = Counter(x.E for x in GA["his"])
    ctl_by_date = defaultdict(list)
    for x in GA["ctl"]:
        ctl_by_date[x.E].append((x.era, x.ticker, x.E))
    rng = np.random.default_rng([SEED, zlib.crc32(BAND_KEY.encode())])
    draws = [rp.sample_control(his_by_date, ctl_by_date, rng)[0] for _ in range(BAND_DRAWS)]
    sims, band, offered, dropped = {}, {}, {}, {}
    for v in VARIANTS:
        T = TT[(v.stop, v.arm)]
        ad = adds.get((v.stop, v.arm), {}) if v.adds else {}
        tr, dr = variant_trades(v, keys_his, T, ad, qqq_of)
        offered[v.name], dropped[v.name] = tr, dr
        sims[v.name] = simulate3(tr, CAP30, calA, startA, risk_of=risk_fn(v, qqq_of), gross_max=v.gross_max)
        band[v.name] = [simulate3(variant_trades(v, ids, T, ad, qqq_of)[0], CAP30, calA, startA, risk_of=risk_fn(v, qqq_of),
                                  gross_max=v.gross_max) for ids in draws]

    # ---- THE BASELINE-PARITY GATE: B0 must BE the first read's cap_30 row
    T0 = TT[("lod", BASE_ARM)]
    bad = parity_trades3(FIRST["first_trades"], orig_keys, res, TT)
    sim0_first = rp.simulate(offered["B0"], CAP30, calA, startA)
    if not curves_equal(sim0_first, sims["B0"]):
        bad.append("simulate3 at its defaults does not equal the first read's simulate on the baseline trades")
    bad += ex.parity_curve(FIRST["first_account_his"], CAP30.name, sims["B0"], calA)
    bad += ex.parity_curve(FIRST["first_account_his"], CAP30.name, sim0_first, calA)
    bad += ex.parity_band(FIRST["first_account_band"], CAP30.name, [s["final"] for s in band["B0"]], sims["B0"]["final"])
    if BASELINE_FINAL_TXT is not None and f"{sims['B0']['final']:.3f}" != BASELINE_FINAL_TXT:
        bad.append(f"the baseline's final equity prints {sims['B0']['final']:.3f}, not the registered {BASELINE_FINAL_TXT}")
    for y, txt in (BASELINE_YEARS_TXT or {}).items():
        if rp.pct(sims["B0"]["yearly"].get(y)) != txt:
            bad.append(f"the baseline's {y} return prints {rp.pct(sims['B0']['yearly'].get(y))}, not the registered {txt}")
    with open(FIRST["first_printout"]) as fh:
        fp = ex.parse_first_printout(fh.read())
    X2 = {"later": {"A": ex.later_rows(S["eras"]["A"])}}
    rc = ex.reentry_count_01(GA["his"], T0, X2, calA)
    if rc != fp["reentry"]:
        bad.append(f"re-entry count {rc} vs the first read's {fp['reentry']}")
    d0 = date_matched3(GA["his"], GA["ctl"], T0, FIRST_DIFF_KEY)["mean R"]
    if tuple(f"{x:+.3f}" for x in (d0["matched"], d0["m_lo"], d0["m_hi"])) != fp["diff"]:
        bad.append(f"date-matched {d0['matched']:+.3f} [{d0['m_lo']:+.3f}, {d0['m_hi']:+.3f}] vs the first read's {fp['diff']}")
    if bad:
        raise GuardStop("BASELINE PARITY FAILED (B0 is not the first read's cap_30 row; no variant number is printed): " + " | ".join(bad[:20]))

    say("\n## The walk")
    say("- " + ", ".join(f"{k} {v:,}" for k, v in sorted(tally.items())))
    say(f"\n## G8 — trade_impact.py on the union of every trade of this read (every stop x exit, adds included, each written as its own "
        f"trade from its own entry date), run BEFORE any number below")
    say(f"- era A: entered after the cutoff {g8['A'][0]}, holds past the last bar kept {g8['A'][1]} (registered: both 0, asserted)")
    say(f"- era B: entered after the cutoff {g8['B'][0]}, holds past the last bar kept {g8['B'][1]} (censored: a walk not mature is in no number)")
    say("\n## BASELINE PARITY — B0 re-walked equals the first read's cap_30 row (asserted before any variant number)")
    say(f"- trades: every ORH5 entry and every p33_s3_t10 AND p33_s3_t20 walk of the {len(orig_keys):,} events equal `trades.tsv.gz`; his "
        f"cap_30 curve equals `account_his.tsv` day by day through the first read's simulate AND through simulate3 (final "
        f"{sims['B0']['final']:.3f} = the registered {BASELINE_FINAL_TXT}; 2020 {rp.pct(sims['B0']['yearly'].get(2020))}, 2021 "
        f"{rp.pct(sims['B0']['yearly'].get(2021))}); the band's five percentiles and share equal `account_band.tsv` (cap_30); re-entry "
        f"count {rc}; date-matched mean R {d0['matched']:+.3f} [{d0['m_lo']:+.3f}, {d0['m_hi']:+.3f}]; every walked ORH5 fill is at "
        f"minute {MIN_FILL_MINUTE} or later")

    # ---- entry facts per stop set
    say("\n## Entry facts per stop set (era A)")
    for s in STOPS:
        for nm in ("his", "ctl", "post"):
            st = Counter(res[k]["sets"][s]["entry"]["status"] + ":" + (res[k]["sets"][s]["entry"]["reason"] or "")
                         for k in ((x.era, x.ticker, x.E) for x in GA[nm]) if k in res)
            say(f"- {s} {nm}: " + ", ".join(f"{k} {v}" for k, v in sorted(st.items())))
    for s in STOPS:
        for nm in ("his", "ctl"):
            fl = [(res[k]["sets"][s]["entry"], X["walk"][k].adr20) for k in ((x.era, x.ticker, x.E) for x in GA[nm])
                  if res[k]["sets"][s]["entry"]["status"] == "filled"]
            if not fl:
                continue
            w = np.array([en["width_pct"] / a for en, a in fl])
            d0n = sum(1 for en, _a in fl if en["day0"]["stopped"])
            say(f"- {s} {nm}: fills {len(fl)}; stop width in ADR20 median {np.median(w):.2f}, 10th pct {np.percentile(w, 10):.2f}, 90th pct "
                f"{np.percentile(w, 90):.2f}; wider than 1 ADR {sum(1 for x in w if x > 1)}; stopped on day 0 {d0n}")
    tw = [x for x in GA["his"] if res[(x.era, x.ticker, x.E)]["sets"]["lod"]["entry"].get("reason") == "too_wide"]
    say(f"- his calls the baseline skipped as too wide ({len(tw)}), and what the other stop sets do with them: "
        + "; ".join(f"{x.ticker} {x.E} (" + ", ".join(
            f"{s} {res[(x.era, x.ticker, x.E)]['sets'][s]['entry']['status'] if res[(x.era, x.ticker, x.E)]['sets'][s]['entry']['status'] == 'filled' else res[(x.era, x.ticker, x.E)]['sets'][s]['entry']['reason']}"
            + (f" {res[(x.era, x.ticker, x.E)]['sets'][s]['entry']['width_pct'] / x.adr20:.1f} ADR" if res[(x.era, x.ticker, x.E)]['sets'][s]['entry'].get('width_pct') else "")
            for s in STOPS) + ")" for x in sorted(tw, key=lambda z: (z.E, z.ticker))))
    for nm in ("his", "ctl"):
        fl = [res[(x.era, x.ticker, x.E)]["own_low"] for x in GA[nm] if res[(x.era, x.ticker, x.E)]["own_low"] is not None
              and res[(x.era, x.ticker, x.E)]["sets"]["lod"]["entry"]["status"] == "filled"]
        say(f"- the baseline's ORH5 stop (inherited by W2 / W3): {nm} fills whose stop is the fill minute's own low (the minute made a new "
            f"low of the day; print-only, the second read's flag) {sum(1 for f in fl if f[0])} of {len(fl)}; fills in minute 0: 0 (asserted)")
    say(f"- W1's stop never reads a minute (daily bars up to D); W1b's lod_prior reads minutes 09:30 .. the minute before the fill")

    # ---- per-trade tables, tail first
    say("\n## HEADLINE — per trade R, tail first (era A; mature trades; exit slippage 0). R = fill - the variant's entry stop: W1 / W1b / "
        "COMBINED are in a WIDER unit (the stop width in ADR20 is printed beside); the account and the band are the comparable numbers")
    rows, widths = [], []
    for vn in TRADE_VARIANTS:
        v = VMAP[vn]
        T = TT[(v.stop, v.arm)]
        for g, lab_ in (("his", "his calls"), ("ctl", "control (same day)")):
            keys = [(x.era, x.ticker, x.E) for x in GA[g]]
            tr, dr = variant_trades(v, keys, T, {}, qqq_of)
            rows.append(ex.trade_row(vn, lab_ + (f" (QQQ-down dropped {dr})" if dr else ""), len(keys) - dr, tr))
            if v.stop != "lod" and g == "his":
                widths.append(f"{vn} his: {width_adr_line(tr, X)}")
    for ln in rp.table(ex.STAT_HDR, rows):
        say(ln)
    say("- W3 / W4m_B0 change only the sizing: their per-trade numbers are B0's; W4m_C / W4a_C / W4ma_C: COMBINED's (an add is its own "
        "trade in the account only)")
    say("- stop width in ADR20 units (his filled trades): " + "; ".join(widths))
    say(f"\n### beside — the near-zero-stop re-read (the second read's R16): the same rows over trades whose stop is at least "
        f"{WIDTH_FLOOR_ADR:g} x our ADR20 wide. A base low just under the fill makes 1R a fraction of a percent and a 5% move reads as 50R; "
        f"the account bounds such a trade by the cap, the per-trade rows and the interval do not. B0 for scale; decides nothing")
    rows, removed = [], []
    for vn in ("B0", "W1", "W1b", "COMBINED"):
        v = VMAP[vn]
        for g, lab_ in (("his", "his calls"), ("ctl", "control (same day)")):
            keys = [(x.era, x.ticker, x.E) for x in GA[g]]
            tr = variant_trades(v, keys, TT[(v.stop, v.arm)], {}, qqq_of)[0]
            fl = [t for t in tr if ex.floor_ok(t, X["walk"])]
            rows.append(ex.trade_row(vn, lab_ + f" (stop >= {WIDTH_FLOOR_ADR:g} ADR)", len(fl), fl))
            removed.append(f"{vn} {g} {len(tr) - len(fl)} of {len(tr)}")
    for ln in rp.table(ex.STAT_HDR, rows):
        say(ln)
    say(f"- trades removed as narrower than {WIDTH_FLOOR_ADR:g} ADR: " + "; ".join(removed))
    for vn in TRADE_VARIANTS:
        v = VMAP[vn]
        parts = []
        for g in ("his", "ctl"):
            keys = [(x.era, x.ticker, x.E) for x in GA[g]]
            op = [t for t in variant_trades(v, keys, TT[(v.stop, v.arm)], {}, qqq_of)[0] if not t.mature]
            parts.append(f"{g} {len(op)} (degraded {sum(1 for t in op if t.status == 'degraded')}; summed booked R {sum(t.realized_r for t in op):+.2f})")
        say(f"- {vn}: trades NOT mature (booked in the account at their last close, in no per-trade number): " + "; ".join(parts))
    for si, s in enumerate(EXIT_SLIPS[1:], start=1):
        parts = []
        for vn in TRADE_VARIANTS:
            v = VMAP[vn]
            for g in ("his", "ctl"):
                keys = [(x.era, x.ticker, x.E) for x in GA[g]]
                r = ex.trade_row(vn, g, len(keys), variant_trades(v, keys, TT[(v.stop, v.arm)], {}, qqq_of)[0], si)
                parts.append(f"{vn} {g} {r[11]}")
        say(f"- exit slippage {100 * s:.1f}% per leg, mean R: " + "; ".join(parts))

    say("\n### beside — COMBINED and B0 on the splits (per trade)")
    rows = []
    for vn in ("B0", "COMBINED"):
        v = VMAP[vn]
        T = TT[(v.stop, v.arm)]
        splits = [("his first breaks", [x for x in GA["his"] if x.retrigger == 0]), ("his retriggers", [x for x in GA["his"] if x.retrigger == 1]),
                  ("his strictly-before", [x for x in GA["his"] if x.strict]), ("his one event per base", [x for x in GA["his"] if x.first_of_base]),
                  ("control first breaks", [x for x in GA["ctl"] if x.retrigger == 0]), ("control retriggers", [x for x in GA["ctl"] if x.retrigger == 1]),
                  ("post-E-only (hindsight)", GA["post"])]
        splits += [(f"{nm} QQQ {q} at D", [x for x in GA[g] if x.qqq == q]) for g, nm in (("his", "his"), ("ctl", "control")) for q in ("up", "mixed", "down")]
        for lab_, evs_ in splits:
            keys = [(x.era, x.ticker, x.E) for x in evs_]
            rows.append(ex.trade_row(vn, lab_, len(keys), [T[k] for k in keys if k in T]))
    for ln in rp.table(ex.STAT_HDR, rows):
        say(ln)

    # ---- by year
    say("\n## By year of E (era A; per trade: n mature / mean R / >=10R per 100)")
    yrs = sorted({x.year for x in GA["his"]} | {x.year for x in GA["ctl"]})
    rows = []
    for vn in TRADE_VARIANTS:
        v = VMAP[vn]
        T = TT[(v.stop, v.arm)]
        for g in ("his", "ctl"):
            keys = [(x.era, x.ticker, x.E) for x in GA[g]]
            tr = [t for t in variant_trades(v, keys, T, {}, qqq_of)[0] if t.mature]
            cells = []
            for y in yrs:
                r = np.array([t.realized_r for t in tr if t.year == y])
                cells.append(f"{len(r)} / {r.mean():+.3f} / {100 * (r >= 10).mean():.1f}" if len(r) else "-")
            rows.append([vn, g] + cells)
    for ln in rp.table(["variant", "group"] + [str(y) for y in yrs], rows):
        say(ln)

    # ---- date-matched differences
    say("\n## HIS minus CONTROL, DATE-MATCHED (era A; per filled mature trade in the cell (date of E, first break / retrigger); month-block, "
        "2,000 resamples, seed 702; B0 uses the first read's key and reproduces it; W3's line IS B0's)")
    diffs = {}
    for vn in TRADE_VARIANTS:
        v = VMAP[vn]
        key = FIRST_DIFF_KEY if vn == "B0" else f"qm_round3|A|{vn}|mean R"
        d = date_matched3(GA["his"], GA["ctl"], TT[(v.stop, v.arm)], key, drop_down_states=(v.sizing == "qqq_drop_down"), qqq_of=qqq_of)
        diffs[vn] = d
        a, b = d["mean R"], d[">=10R /100"]
        say(f"- {vn} (his {d['_n'][0]} / control {d['_n'][1]} mature trades): mean R {a['matched']:+.3f} [{a['m_lo']:+.3f}, {a['m_hi']:+.3f}]; "
            f">=10R per 100 {b['matched']:+.2f} [{b['m_lo']:+.2f}, {b['m_hi']:+.2f}] | cells uncovered {a['cells_uncovered']} "
            f"({a['his_uncovered']} of his), resamples dropped {a['dropped_m']}")
    for vn in ("W1", "W1b", "COMBINED"):
        v = VMAP[vn]
        d = date_matched3(GA["his"], GA["ctl"], TT[(v.stop, v.arm)], f"qm_round3|A|{vn}|floor|mean R", keep=lambda t: ex.floor_ok(t, X["walk"]))
        a = d["mean R"]
        say(f"- beside, {vn} over stops >= {WIDTH_FLOOR_ADR:g} ADR only (his {d['_n'][0]} / control {d['_n'][1]}): mean R {a['matched']:+.3f} "
            f"[{a['m_lo']:+.3f}, {a['m_hi']:+.3f}] (decides nothing)")

    # ---- the account
    say(f"\n## ACCOUNT CURVE — his calls, chronological (era A; start 1.0; every variant at the 30% cap: 1% risk unless W3, 30% position cap, "
        f"30% per stock at cost; no margin unless W4m)")
    hdr = ["variant", "stop", "exit", "sizing", "gross max"] + [f"{y} return" for y in rp.FORK_YEARS] + [
        "2022 (exits only)", "final equity", "max drawdown", "trades offered", "of them adds", "not offered (QQQ down)", "entered",
        "at 1% / at 0.5%", "skipped no room", "skipped stock limit", "trimmed to the stock limit", "cap bound", "max open", "max gross",
        "deepest cash"]
    rows = []
    for v in VARIANTS:
        sim = sims[v.name]
        c = sim["counts"]
        tr = offered[v.name]
        n_add = sum(1 for t in tr if "|add" in t.key[2])
        rows.append([v.name + (" (beside)" if v.beside else ""), v.stop, v.arm, v.sizing, f"{v.gross_max:g}x"]
                    + [rp.pct(sim["yearly"].get(y)) for y in rp.FORK_YEARS]
                    + [rp.pct(sim["yearly"].get(2022)), f"{sim['final']:.3f}", rp.pct(sim["max_dd"]), len(tr), n_add, dropped[v.name],
                       c["entered"], f"{c.get('risk_0.01', 0)} / {c.get('risk_0.005', 0)}", c["skipped_no_room"], c["skipped_stock_limit"],
                       c["stock_limit_trimmed"], c["cap_bound"], sim["max_open"], rp.pct(sim["max_gross"]), f"{sim['min_cash']:+.3f}"])
    for ln in rp.table(hdr, rows):
        say(ln)
    for v in VARIANTS:
        sim = sims[v.name]
        say(f"- {v.name}: year-end equity " + ", ".join(f"{y} {q:.3f}" for y, q in sorted(sim["year_end"].items()))
            + "; entered per year " + ", ".join(f"{y} {n}" for y, n in sorted(sim["entered_by_year"].items()))
            + "; skipped per year " + ", ".join(f"{y} {n}" for y, n in sorted(sim["skipped_by_year"].items())))
    for combo, rs in add_reasons.items():
        his_adds = sum(1 for k in adds[combo] if k in set(keys_his))
        say(f"- W4a adds on the {combo[0]} x {combo[1]} trades (every group): " + ", ".join(f"{k} {v}" for k, v in sorted(rs.items()))
            + f"; his calls' adds {his_adds}")

    # ---- the stop x exit grid (beside)
    say("\n### beside — every stop x every exit at the 30% cap, flat 1% risk (his calls; decides nothing)")
    rows = []
    for s in STOPS:
        for a in ARMS:
            T = TT[(s, a)]
            tr = [T[k] for k in keys_his if k in T]
            sim = rp.simulate(tr, CAP30, calA, startA)
            mat = [t.realized_r for t in tr if t.mature]
            rows.append([s, a, len(tr), f"{np.mean(mat):+.3f}" if mat else "-", f"{100 * np.mean(np.array(mat) >= 10):.1f}" if mat else "-",
                         rp.pct(sim["yearly"].get(2020)), rp.pct(sim["yearly"].get(2021)), f"{sim['final']:.3f}", rp.pct(sim["max_dd"])])
    for ln in rp.table(["stop", "exit", "his trades", "mean R", ">=10R /100", "2020", "2021", "final equity", "max drawdown"], rows):
        say(ln)

    # ---- the band
    say(f"\n## CONTROL BAND — the first read's {BAND_DRAWS} same-day draws (seed {SEED}, key `{BAND_KEY}`), each drawn control event "
        f"mapped to its trade under the variant (its add too under W4a)")
    rows, band_out, shares = [], [], {}
    for v in VARIANTS:
        bs_sims = band[v.name]
        hs = sims[v.name]
        for y in ex.FORK_YEARS + ("final", "max_dd"):
            vals = [s["yearly"].get(y) for s in bs_sims] if isinstance(y, int) else [s[y] for s in bs_sims]
            hv = hs["yearly"].get(y) if isinstance(y, int) else hs[y]
            bsum = rp.band_summary(vals)
            share = (sum(1 for q in vals if q is not None and hv is not None and q >= hv) / len(vals)) if (hv is not None and vals) else float("nan")
            shares[(v.name, y)] = share
            band_out.append((v.name, y, bsum, hv, share))
            rows.append([v.name, {"final": "final equity", "max_dd": "max drawdown (higher = WORSE)"}.get(y, f"{y} return"),
                         rp.fmt(hv, 3), rp.fmt(bsum.get(5), 3), rp.fmt(bsum.get(50), 3), rp.fmt(bsum.get(95), 3), rp.pct(share)])
    for ln in rp.table(["variant", "year / measure", "his calls", "control 5th pct", "control median", "control 95th pct",
                        "share of draws >= his (for max drawdown: as deep or DEEPER, i.e. worse)"], rows):
        say(ln)

    # ---- the fork
    fv = VMAP[FORK_VARIANT]
    verdict, years_met, band_met, yrs_ = ex.fork_exec(sims[FORK_VARIANT]["yearly"], shares[(FORK_VARIANT, "final")])
    say(f"\n## THE FORK (registered before any outcome; era A, COMBINED = W1 + W2 + W3 at the 30% cap: the base-low stop, the speed trail, "
        f"QQQ sizing; applied to his calls and to the control)")
    say(f"- yearly return >= +{100 * ex.FORK_RET:.0f}% in BOTH 2020 and 2021: " + ", ".join(f"{y} {rp.pct(r)}" for y, r in yrs_.items())
        + f" -> {'MET' if years_met else 'not met'}")
    say(f"- the same-day band at or above his final equity ({sims[FORK_VARIANT]['final']:.3f}) in {rp.pct(shares[(FORK_VARIANT, 'final')])} "
        f"of {BAND_DRAWS} draws (needs <= {rp.pct(ex.BAND_SHARE_MAX, 0)}) -> {'MET' if band_met else 'not met'}")
    say(f"- VERDICT: **{verdict}** — {FORK_TEXT[verdict]}")
    say("- read with it: every variant here was chosen AFTER the first two reads (the stop-out count, the 20-day trail's mean, the 30%-cap "
        "row, the market splits); a variant that helps must still be validated on calls not used here. W4 (margin, adds) is beside and "
        "decides nothing in any reading.")

    # ---- beside: the strictly-before calls under COMBINED
    strict = [x for x in GA["his"] if x.strict]
    Tf = TT[(fv.stop, fv.arm)]
    st_tr, _d = variant_trades(fv, [(x.era, x.ticker, x.E) for x in strict], Tf, {}, qqq_of)
    st_sim = simulate3(st_tr, CAP30, calA, startA, risk_of=risk_fn(fv, qqq_of))
    rng = np.random.default_rng([SEED, zlib.crc32(STRICT_BAND_KEY.encode())])
    st_draws = [rp.sample_control(Counter(x.E for x in strict), ctl_by_date, rng)[0] for _ in range(BAND_DRAWS)]
    st_fin = [simulate3(variant_trades(fv, ids, Tf, {}, qqq_of)[0], CAP30, calA, startA, risk_of=risk_fn(fv, qqq_of))["final"] for ids in st_draws]
    st_share = sum(1 for q in st_fin if q >= st_sim["final"]) / len(st_fin) if st_fin else float("nan")
    say(f"- BESIDE (decides nothing): COMBINED on the {len(strict)} strictly-before calls (clean of E's bar): yearly "
        + ", ".join(f"{y} {rp.pct(q)}" for y, q in sorted(st_sim["yearly"].items()) if y in rp.FORK_YEARS)
        + f", final {st_sim['final']:.3f}; their own same-day band (the first read's strictly-before draws) at or above it in {rp.pct(st_share)}")

    # ---- era B, descriptive
    GB = groups["B"]
    calB = S["Ds"]["B"].cal
    say("\n## Era B (descriptive; 9 calls, 345 control events)")
    rows = []
    for vn in TRADE_VARIANTS:
        v = VMAP[vn]
        for g in ("his", "ctl"):
            keys = [(x.era, x.ticker, x.E) for x in GB[g]]
            tr, dr = variant_trades(v, keys, TT[(v.stop, v.arm)], {}, qqq_of)
            rows.append(ex.trade_row(vn, g, len(keys) - dr, tr))
    for ln in rp.table(ex.STAT_HDR, rows):
        say(ln)
    for v in VARIANTS:
        keys = [(x.era, x.ticker, x.E) for x in GB["his"]]
        tr, _d = variant_trades(v, keys, TT[(v.stop, v.arm)], adds.get((v.stop, v.arm), {}) if v.adds else {}, qqq_of)
        if tr:
            sB = simulate3(tr, CAP30, calB, min(t.e_ci for t in tr), risk_of=risk_fn(v, qqq_of), gross_max=v.gross_max)
            say(f"- era B his {v.name}: {len(tr)} trades, yearly " + ", ".join(f"{y} {rp.pct(q)}" for y, q in sorted(sB["yearly"].items()))
                + f", final {sB['final']:.3f}, max drawdown {rp.pct(sB['max_dd'])}")

    # ---- outputs
    write_outputs(S, X, res, TT, adds, qqq_of, sims, band_out)


def write_outputs(S: dict, X: dict, res: dict, TT: dict, adds: dict, qqq_of: dict, sims: dict, band_out: list) -> None:
    cols = ["era", "ticker", "D", "E", "base_id", "retrigger", "is_his", "is_ctl", "is_post", "is_strict", "qqq_at_D", "adr20", "base_low",
            "stop_set", "entry_status", "entry_reason", "fill", "stop", "fill_minute", "width_pct", "width_adr", "own_low", "arm", "status",
            "mature", "sessions_held", "realized_r", "r_exit_slip_0.1", "r_exit_slip_0.2", "legs"]
    with gzip.open(os.path.join(OUT_DIR, "trades.tsv.gz"), "wt") as fh:
        fh.write("\t".join(cols) + "\n")
        for k, w in sorted(res.items()):
            ev = X["walk"][k]
            for s in STOPS:
                en = w["sets"][s]["entry"]
                base = [ev.era, ev.ticker, ev.D, ev.E, ev.base_id, ev.retrigger, int(ev.his), int(ev.ctl), int(ev.post), int(ev.strict), ev.qqq,
                        ev.adr20, X["base_low"][k], s, en["status"], en["reason"] or "", en.get("fill"), en.get("stop"), en.get("fill_minute"),
                        en.get("width_pct"), (en["width_pct"] / ev.adr20) if en.get("width_pct") else None,
                        ("" if w["own_low"] is None else int(w["own_low"][0]))]
                if not w["sets"][s]["arms"]:
                    fh.write("\t".join("" if x is None else (f"{x:.10g}" if isinstance(x, float) else str(x)) for x in base + [""] * 8) + "\n")
                    continue
                for a in ARMS:
                    t = TT[(s, a)][k]
                    legs = ";".join(f"{lg[5]}:{lg[4]}:{lg[2]:.6f}:{lg[3]:.6f}" for lg in t.legs)
                    row = base + [a, t.status, int(t.mature), t.sessions_held, t.realized_r, t.r_slip[1], t.r_slip[2], legs]
                    fh.write("\t".join("" if x is None else (f"{x:.10g}" if isinstance(x, float) else str(x)) for x in row) + "\n")
    with open(os.path.join(OUT_DIR, "adds.tsv"), "w") as fh:
        fh.write("era\tstop_set\tarm\tticker\torigin_E\tadd_date\tsession_j\tfill\tstop\twidth_pct\texit_px\texit_session\trealized_r\tqqq_at_add_D\tmature\n")
        for (s, a), ad in sorted(adds.items()):
            for k, t in sorted(ad.items()):
                cal = S["Ds"][t.era].cal
                j = int(t.key[2].split("|add")[1])
                fh.write(f"{t.era}\t{s}\t{a}\t{t.ticker}\t{k[2]}\t{cal[t.e_ci]}\t{j}\t{t.fill:.10g}\t{t.stop:.10g}\t{t.width:.10g}\t{t.legs[0][3]:.10g}\t"
                         f"{j + t.sessions_held}\t{t.realized_r:.10g}\t{qqq_of.get(t.key, '')}\t{int(t.mature)}\n")
    calA = S["Ds"]["A"].cal
    with open(os.path.join(OUT_DIR, "account_his.tsv"), "w") as fh:
        fh.write("variant\tdate\tequity\n")
        for vn, sim in sims.items():
            for ci, eq in zip(*sim["curve"]):
                fh.write(f"{vn}\t{calA[ci]}\t{eq:.10f}\n")
    with open(os.path.join(OUT_DIR, "account_band.tsv"), "w") as fh:
        fh.write("variant\tmeasure\this\tp5\tp25\tp50\tp75\tp95\tshare_ge_his\n")
        for vn, y, bs, hv, sg in band_out:
            fh.write("\t".join(str(x) for x in (vn, y, hv, bs.get(5), bs.get(25), bs.get(50), bs.get(75), bs.get(95), sg)) + "\n")


if __name__ == "__main__":
    sys.exit(main())
