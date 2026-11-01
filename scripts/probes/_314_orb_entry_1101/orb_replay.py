#!/usr/bin/env python3
"""#314 — the parabolic short re-walked on HIS entry and stop: short the opening-range-low break on D0+1, stop at the day's high,
Russo's 1-3 session limit. Registration: docs/analysis/parabolic_short_orb_entry_prereg_2026-11-01.md (read it first; every number
here is the plan's, none is tuned here).

Stages (each its own invocation):
  --dry-run   the synthetic fixtures of orb_goldens.py through `walk_episode` + synthetic end-to-end trees through the --walk path
              (the clean tree, then the refusal trees: a doubled-price pull, a split in the walk, a delisted owner); writes dry_run.txt.
              Opens no real input.
  --request   writes minute_request.tsv from the pinned climax list and the two calendars (pins checked); refuses if it exists.
  --walk      the ONE run: refuses unless every data pin matches, the code pins written ABOVE the doc's marker match this file, the
              goldens and the request on disk, the post-pull pins (freeze_commit, doc_body, minute_bars, minute_bars_meta) are pasted
              under the doc's <!-- FREEZE --> line, the committed copies at freeze_commit equal the files on disk, the pull's sidecar
              declares feed=sip adjustment=raw tz=America/New_York, dry_run.txt ends DRY RUN COMPLETE and result.txt does not exist.
              Writes result.txt + episodes_orb.tsv. Refuses (no result.txt) when the pull fails its own check: more than
              REFUSE_SHARE of the walked sessions present outside the basis or shape bands.

Guards: no network, no DB, no production server, no subagent; nothing dated 2025-01-01 or later is read from any bar file (the seal,
#710); the 10-28 helpers are IMPORTED (ps_common / ps_walk by path), never copied.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
BUILD = os.path.join(REPO, "scripts", "probes", "_314_replay_build")
for p in (REPO, BUILD, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)
import ps_common as X  # noqa: E402  (the 10-28 shared module: constants, loaders, sha, freeze helpers, Say / Claims)
import ps_walk as W    # noqa: E402  (mean_ci, base_verdict, tail_clause, verdict_three_ways, ending_class)
import orb_goldens as G  # noqa: E402

GuardStop = X.GuardStop
DOC = os.path.join(REPO, "docs", "analysis", "parabolic_short_orb_entry_prereg_2026-11-01.md")
SEAL_FIRST = "2025-01-01"                       # nothing dated here or later is read
SEAL = X.CUT_B                                  # 2024-12-31
ORB_MINUTES, ORB_PRIMARY = (1, 5, 15), 5
HOLDS, HOLD_PRIMARY = (1, 2, 3), 3
TICK = 0.01
R_FLOOR = 0.01                                  # (stop - entry) / entry under this = void_bad_geometry
BASIS_BAND = (0.90, 1.10)                       # minute RTH low / daily RAW low: outside = basis_mismatch (a wrong symbol, year or basis)
SHAPE_BAND = (0.98, 1.02)                       # minute RTH high / daily RAW high AND low / low, each: outside = shape_mismatch (wrong feed, shifted clock)
REFUSE_SHARE = 0.02                             # (basis + shape failures) / sessions checked above this -> the RUN refuses (the pull is wrong)
SLIP_TICKS = (0.01, 0.02, 0.05)                 # the tick-slippage beside rows: entry k lower, every cover k higher -> R_k = R - 2k / risk
OPEN_MIN, END_MIN, EARLY_END_MIN = 9 * 60 + 30, 16 * 60, 13 * 60
EARLY_CLOSE = frozenset(X.C.EARLY_CLOSE)        # the 13:00 closes (asis_common)
SLIPPAGES = X.SLIPPAGES                         # (0.0, 0.001, 0.002)
HAIRCUT = X.HAIRCUT                             # 1.25
TOL = G.TOL
VARIANTS = [f"o{o}h{h}" for o in ORB_MINUTES for h in HOLDS]
PRIMARY = f"o{ORB_PRIMARY}h{HOLD_PRIMARY}"
BESIDE = PRIMARY + "x"                          # the primary under the first draft's stop rule (the entry bar's high inside the stop): beside, never deciding
ALL_VARIANTS = VARIANTS + [BESIDE]
POPS = ("P1", "P2", "P2small")
DECIDING = ("P1", "P2")
META_REQUIRED = {"feed": "sip", "adjustment": "raw", "tz": "America/New_York"}
CODE_PIN_KEYS = ("orb_replay.py", "orb_goldens.py", "minute_request", "dry_run")      # pinned ABOVE the marker (the pre-pull freeze)
POST_PULL_KEYS = ("freeze_commit", "doc_body", "minute_bars", "minute_bars_meta")   # pasted BELOW the marker by the main loop
GIT_PATHS = {"orb_replay.py": "scripts/probes/_314_orb_entry_1101/orb_replay.py", "orb_goldens.py": "scripts/probes/_314_orb_entry_1101/orb_goldens.py",
             "minute_request": "scripts/probes/_314_orb_entry_1101/minute_request.tsv", "dry_run": "scripts/probes/_314_orb_entry_1101/dry_run.txt",
             "doc": "docs/analysis/parabolic_short_orb_entry_prereg_2026-11-01.md"}

# the registration's §7 pins — every DATA input and imported module this code opens; the run refuses on any mismatch
REGISTERED_PINS = {
    "climax_list": "53af1961b7b0a19325d378433f150fccd0253dc3498a8b05b83e73aa78facf6a",
    "episodes": "5a712f21d29a0d4a0cedd71d03b28d0d3cf4d3e87a33b896bbadbc4ccf9e8b89",
    "calendar_B": "a17d991a25a1b6b6977c388f352213142868635f94c2010813a7a0f8ef79d2be",
    "sessions_A": "098a9b50c92a1045043bc089a4d4d600a9631bdb45a8e22969d872440672f2f0",
    "export_A": "0d5d2d0eb027abc06e4186ddec7d1e8b1234fd86f92c26798a8e15f113db668d",
    "raw_A": "f978db45074e9109178a1755c232fa1e684a6f83dab96ab007a26b12008f1444",
    "export_B": "ccc0097fe535cb8de9b83d6d534744b6cbadc114d9d29ecac677ac18a52900ba",
    "splits_B": "3199d06d5fb7dcd52ebd34e8c71e148b45ec0ca4a15f7f03ea1b715718882b0b",
    "ps_common.py": "6f99467e3a2bc5c36292b87d875a469a7571000b240c663632862722d8bccc10",
    "ps_walk.py": "a4decccfebb4d49dd6328163f12a1bc1624513ae7a196ecf3ea41d9f48762cb0",
    "asis_common.py": "4d36d6a42532dc782b7ccdce86a530a3b0bd948f66db74d5f1ab7af79a4562c4",
    "runner.py": "a4f016720f8226933367ae3d776a7067d9d94dea634b28e5e5685e186bc3ad69",
    "consolidation_breakout.py": "e14027be38b24352dd3c19fd5a1dcd54bae2e1cf80fc58a064d1ea65c821861b",
}
REQUEST_PIN_KEYS = ("climax_list", "calendar_B", "sessions_A")

# the 10-28 primary, printed beside (ps_replay_result.txt, pooled lines)
BASELINE_1028 = {
    "P1": "n 252, mean R +0.0767 [-0.0429, +0.1975], ADR P&L +0.2599, >= 3R 0 (CAN'T TELL)",
    "P2": "n 168, mean R -0.0670 [-0.1818, +0.0551], ADR P&L -0.3119, >= 3R 0 (CAN'T TELL)",
    "P2small": "n 133, mean R -0.0564 [-0.1641, +0.0685], ADR P&L -0.2724, >= 3R 0 (CAN'T TELL)",
}
EXPECTATIONS = (   # (label, lo, hi) on the printed share; a miss is printed first and changes no rule
    ("triggered share of the pre-walk population in [0.40, 0.85]", 0.40, 0.85),
)


def parse_variant(v: str) -> tuple:
    """'o5h3' -> (5, 3, 'prior'); 'o5h3x' -> (5, 3, 'through') the beside stop rule; 'o5h3+' -> the primary (an extra claims key)."""
    m = re.fullmatch(r"o(\d+)h(\d)([x+]?)", v)
    if not m:
        raise GuardStop(f"variant {v!r} is not o<range>h<hold>[x]")
    return int(m.group(1)), int(m.group(2)), ("through" if m.group(3) == "x" else "prior")


class Paths:
    """Every file this code opens (overridable for the synthetic end-to-end tree)."""

    def __init__(self, data: str = "/Users/alvinfung/apollo_data", here: str = HERE, doc: str = DOC, pins: dict = None):
        self.data, self.here, self.doc = data, here, doc
        self.pins = dict(REGISTERED_PINS if pins is None else pins)
        self.files = {
            "climax_list": f"{data}/ps314/climax_list.tsv", "episodes": f"{data}/ps314/episodes.tsv",
            "calendar_B": f"{data}/ps314/calendar_B.txt", "sessions_A": f"{data}/cb702_pre_v2/sessions.txt",
            "export_A": f"{data}/cb702_pre_v2/daily_closes_all.csv.gz", "raw_A": f"{data}/cb702_pre_v2/daily_raw_close.csv.gz",
            "export_B": f"{data}/cb702/daily_closes_all.csv.gz", "splits_B": f"{data}/cb702/cb702_splits.psv",
            "ps_common.py": os.path.join(BUILD, "ps_common.py"), "ps_walk.py": os.path.join(BUILD, "ps_walk.py"),
            "asis_common.py": os.path.join(REPO, "scripts", "probes", "_705_asis_1026", "asis_common.py"),
            "runner.py": os.path.join(REPO, "scripts", "probes", "_cb_backtest", "runner.py"),
            "consolidation_breakout.py": os.path.join(REPO, "agents", "market_intelligence", "consolidation_breakout.py"),
        }

    def f(self, k: str) -> str:
        return self.files[k]

    @property
    def minute_bars(self): return os.path.join(self.here, "minute_bars.csv.gz")
    @property
    def minute_meta(self): return os.path.join(self.here, "minute_bars.meta.json")
    @property
    def request(self): return os.path.join(self.here, "minute_request.tsv")
    @property
    def dry(self): return os.path.join(self.here, "dry_run.txt")
    @property
    def result(self): return os.path.join(self.here, "result.txt")
    @property
    def refused(self): return os.path.join(self.here, "result.refused.txt")
    @property
    def episodes_out(self): return os.path.join(self.here, "episodes_orb.tsv")

    def code_pins(self) -> dict:
        """The four files pinned above the doc's marker, as they are on disk now."""
        return {"orb_replay.py": X.sha(os.path.abspath(__file__)), "orb_goldens.py": X.sha(G.__file__),
                "minute_request": X.sha_or_absent(self.request), "dry_run": X.sha_or_absent(self.dry)}


def pin_problems(P: Paths, keys=None) -> list:
    out = []
    for k, want in P.pins.items():
        if keys is not None and k not in keys:
            continue
        got = X.sha_or_absent(P.f(k))
        if got != want:
            out.append(f"{k}: {got[:16]} != pinned {want[:16]} ({P.f(k)})")
    return out


# ═════════════════════════════════════════════════════════════════════════════════════════════
# minute bars
# ═════════════════════════════════════════════════════════════════════════════════════════════
def minute_of(ts: str) -> int:
    """'HH:MM' or 'HH:MM:00' -> minute of the day. Anything else refuses."""
    s = ts.strip()
    if len(s) == 8 and s[5:] == ":00":
        s = s[:5]
    if len(s) != 5 or s[2] != ":" or not (s[:2].isdigit() and s[3:].isdigit()):
        raise GuardStop(f"minute bars: ts_et {ts!r} is not HH:MM (ET bar start)")
    return int(s[:2]) * 60 + int(s[3:])


def rth(bars: list, session: str) -> list:
    """The regular-hours bars of one session, sorted: start minute in [09:30, 16:00), and before 13:00 on an early close."""
    end = EARLY_END_MIN if session in EARLY_CLOSE else END_MIN
    out = [b for b in bars if OPEN_MIN <= b[0] < end]
    out.sort(key=lambda b: b[0])
    for a, b in zip(out, out[1:]):
        if a[0] == b[0]:
            raise GuardStop(f"minute bars: duplicate minute {b[0] // 60:02d}:{b[0] % 60:02d} on {session}")
    return out


def bars_from_fixture(rows: list) -> list:
    return [(minute_of(ts), float(o), float(h), float(l), float(c)) for ts, o, h, l, c in rows]


def load_minute_file(path: str, wanted: set) -> tuple:
    """{(ticker, session): [(minute, o, h, l, c), ...]} for the wanted (ticker, session) pairs; refuses a row dated >= 2025-01-01, a
    duplicate minute, a non-finite price. -> (bars, info)."""
    import pandas as pd
    out, info = defaultdict(list), Counter()
    with gzip.open(path, "rt") as fh:
        for ch in pd.read_csv(fh, dtype={"ticker": str, "session_date": str, "ts_et": str}, chunksize=500_000):
            info["rows_read"] += len(ch)
            if (ch["session_date"] >= SEAL_FIRST).any():
                raise GuardStop(f"minute bars: a row dated >= {SEAL_FIRST} (the seal) is in {path}")
            keep = [(t, d) in wanted for t, d in zip(ch["ticker"], ch["session_date"])]
            ch = ch[keep]
            info["rows_wanted"] += len(ch)
            for t, d, ts, o, h, l, c in zip(ch["ticker"], ch["session_date"], ch["ts_et"], ch["open"], ch["high"], ch["low"], ch["close"]):
                vals = (float(o), float(h), float(l), float(c))
                if not all(math.isfinite(v) and v > 0 for v in vals):
                    raise GuardStop(f"minute bars: a non-finite or non-positive price for {t} {d} {ts}")
                out[(t, d)].append((minute_of(str(ts)),) + vals)
    info["pairs"] = len(out)
    return dict(out), info


def meta_problems(path: str, request_sha: str) -> list:
    """The pull's sidecar: feed / adjustment / tz as registered, and the request it served."""
    if not os.path.exists(path):
        return [f"{path} is absent (the pull writes it: feed, adjustment, tz, request_sha256)"]
    try:
        meta = json.load(open(path))
    except Exception as ex:                                 # noqa: BLE001
        return [f"{path} is not JSON ({ex})"]
    out = [f"sidecar {k} = {meta.get(k)!r}, registered {v!r}" for k, v in META_REQUIRED.items() if str(meta.get(k, "")).lower() != v.lower()]
    if meta.get("request_sha256") != request_sha:
        out.append(f"sidecar request_sha256 {str(meta.get('request_sha256'))[:16]} != minute_request.tsv on disk {request_sha[:16]}")
    return out


# ═════════════════════════════════════════════════════════════════════════════════════════════
# one walk (pure; the registration's §3)
# ═════════════════════════════════════════════════════════════════════════════════════════════
def blank() -> dict:
    return {"status": "", "reason": "", "orb_low": None, "orb_high": None, "entry_session": "", "entry_ts": "", "entry": None, "stop": None,
            "risk": None, "ambiguous_entry_bar": None, "exit_session": "", "exit_ts": "", "exit": None, "r": None, "mfe": None, "mae": None,
            "sessions_held": None, "last_session": "", "last_close": None, "r_last_close": None, "r_haircut": None, "ended_class": "",
            "one_day_fall": None, "r_slip1": None, "r_slip2": None, "r_tick1": None, "r_tick2": None, "r_tick5": None, "pnl_adr": None,
            "pnl_adr_slip1": None, "pnl_adr_slip2": None, "pnl_adr_tick1": None, "pnl_adr_tick2": None, "pnl_adr_tick5": None,
            "pnl_adr_last_close": None, "pnl_adr_haircut": None, "win": None}


def hhmm(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"


def walk_episode(sessions: list, minutes: dict, daily_state, orb_minutes: int, hold: int, stop_rule: str = "prior") -> dict:
    """sessions = [D0+1, D0+2, D0+3] (ISO); minutes = {session: [(minute, o, h, l, c), ...] | None (absent)}; daily_state(session) ->
    'bar' | 'hole' | 'ended'. Short the first bar after the opening range whose low <= ORB low - 1c (fill at that level, or at the open
    on a gap through); stop = the session's highest high BEFORE the entry bar + 1c (`stop_rule` 'prior', registered) — an entry bar
    whose own high reaches it books the stop on that bar (-1R; `ambiguous_entry_bar` = 1); the stop is live on every later bar; cover
    at the close of the `hold`-th session's last bar; the stop before the time exit on that bar. One leg, no target.
    `stop_rule` 'through' = the first draft's rule (the entry bar's high inside the stop): the beside row only, never deciding."""
    if stop_rule not in ("prior", "through"):
        raise GuardStop(f"stop_rule {stop_rule!r}")
    o = blank()
    entered = False
    entry = stop = risk = None
    mfe_low = mae_high = None
    last_close, last_session = None, ""
    for k, s in enumerate(sessions[:hold], start=1):
        st = daily_state(s)
        if st == "ended":
            if entered:
                o.update(status="ended_mid_walk", reason="series_end", last_session=last_session, last_close=last_close, sessions_held=k - 1,
                         mfe=(entry - mfe_low) / risk if mfe_low is not None else 0.0, mae=(mae_high - entry) / risk if mae_high is not None else 0.0)
            else:
                o.update(status="ended_before_entry", reason="series_end")
            return o
        if st == "hole":
            o.update(status="hole_open" if entered else "hole", reason="hole")
            return o
        raw = minutes.get(s)
        bars = rth(raw, s) if raw is not None else []
        if not bars:
            o.update(status="minute_missing_open" if entered else "minute_missing", reason="minute_missing")
            return o
        scan = bars
        if k == 1:
            orb = [b for b in bars if b[0] < OPEN_MIN + orb_minutes]
            if not orb or orb[0][0] != OPEN_MIN:            # the range needs the opening minute itself (a 09:30 bar); a late first print is no range
                o.update(status="no_orb", reason="no_orb")
                return o
            orb_low, day_high = min(b[3] for b in orb), max(b[2] for b in orb)
            level = round(orb_low - TICK, 4)
            o.update(orb_low=orb_low, orb_high=day_high)
            scan = [b for b in bars if b[0] >= OPEN_MIN + orb_minutes]
        for i, b in enumerate(scan):
            m, bo, bh, bl, bc = b
            is_exit_bar = (k == hold and i == len(scan) - 1)
            if not entered:
                if bl > level:                              # no trigger: this bar's high joins the day's high for a later entry
                    day_high = max(day_high, bh)
                    continue
                entry = level if bo >= level else bo
                if stop_rule == "through":
                    day_high = max(day_high, bh)
                stop = round(day_high + TICK, 4)
                risk = stop - entry
                entered = True
                o.update(entry_session=s, entry_ts=hhmm(m), entry=entry, stop=stop, risk=risk, ambiguous_entry_bar=int(bh >= stop))
                if risk / entry < R_FLOOR:
                    o.update(status="void_bad_geometry", reason="void_bad_geometry")
                    return o
                if bh >= stop:                              # the entry bar itself reaches the stop: the order of its prints is unknown -> the stop (adverse)
                    return settle(o, s, m, stop, "stop", k, entry, risk, None, stop)
                if is_exit_bar:                             # entered on the last bar of the last session: the time exit is this bar's close
                    return settle(o, s, m, bc, "time_stop", k, entry, risk, None, None)
                continue
            if bo >= stop:
                return settle(o, s, m, bo, "stop", k, entry, risk, mfe_low, max(mae_high or entry, bo))
            if bh >= stop:
                return settle(o, s, m, stop, "stop", k, entry, risk, mfe_low, max(mae_high or entry, stop))
            mae_high = bh if mae_high is None else max(mae_high, bh)
            mfe_low = bl if mfe_low is None else min(mfe_low, bl)
            if is_exit_bar:
                return settle(o, s, m, bc, "time_stop", k, entry, risk, mfe_low, mae_high)
        if k == 1 and not entered:
            o.update(status="untriggered", reason="untriggered")
            return o
        last_close, last_session = bars[-1][4], s
    raise GuardStop("walk: fell through the sessions with the position open (the exit bar rule cannot have run)")


def settle(o: dict, s: str, m: int, px: float, reason: str, k: int, entry: float, risk: float, mfe_low, mae_high) -> dict:
    r = (entry - px) / risk
    o.update(status="settled", reason=reason, exit_session=s, exit_ts=hhmm(m), exit=px, r=r, sessions_held=k,
             mfe=(entry - mfe_low) / risk if mfe_low is not None else 0.0, mae=(mae_high - entry) / risk if mae_high is not None else 0.0,
             r_slip1=(entry - px * (1.0 + SLIPPAGES[1])) / risk, r_slip2=(entry - px * (1.0 + SLIPPAGES[2])) / risk, win=int(r > 0))
    for k_, t in zip((1, 2, 5), SLIP_TICKS):
        o[f"r_tick{k_}"] = r - 2.0 * t / risk               # entry t lower, the cover t higher; the planned R (stop - entry) is the unit
    return o


def book_ended(o: dict, closes: list, raw_last: float) -> dict:
    """ended_mid_walk: R at the last minute close and at the adverse haircut (ps_walk.ending_class on the daily closes)."""
    if o["status"] != "ended_mid_walk":
        return o
    cls, fall = W.ending_class([{"close": c} for c in closes], raw_last, len(closes) - 1)
    hair = HAIRCUT if (cls == "collapse" or (cls == "other" and fall <= X.ONE_DAY_FALL)) else 1.0
    e, r = o["entry"], o["risk"]
    o.update(ended_class=cls, one_day_fall=fall, r_last_close=(e - o["last_close"]) / r, r_haircut=(e - o["last_close"] * hair) / r)
    return o


def add_pnl(o: dict, adr20) -> dict:
    if adr20 in (None, "") or float(adr20) <= 0 or o["entry"] is None:
        return o
    a, e = float(adr20), o["entry"]
    if o["status"] == "settled":
        px = o["exit"]
        o.update(pnl_adr=(e - px) / e / a, pnl_adr_slip1=(e - px * (1.0 + SLIPPAGES[1])) / e / a, pnl_adr_slip2=(e - px * (1.0 + SLIPPAGES[2])) / e / a)
        for k_, t in zip((1, 2, 5), SLIP_TICKS):
            o[f"pnl_adr_tick{k_}"] = (e - t - (px + t)) / e / a
    elif o["status"] == "ended_mid_walk" and o["r_last_close"] is not None:
        hair = o["r_haircut"] * o["risk"]
        o.update(pnl_adr_last_close=(e - o["last_close"]) / e / a, pnl_adr_haircut=hair / e / a)
    return o


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the dry run (§8): the fixtures through walk_episode, then synthetic trees through the whole --walk path
# ═════════════════════════════════════════════════════════════════════════════════════════════
def run_fixture(name: str, fx: dict, variant: str) -> dict:
    orb, hold, rule = parse_variant(variant)
    minutes = {s: (bars_from_fixture(b) if b is not None else None) for s, b in fx["minutes"].items()}
    o = walk_episode(list(G.SESSIONS), minutes, lambda s: fx["daily"].get(s, "bar"), orb, hold, rule)
    o = book_ended(o, fx.get("closes", []), fx.get("raw_last", 1.0))
    return add_pnl(o, fx.get("adr20"))


def dry_run(P: Paths, say=None) -> int:
    say = say or X.Say()
    say(f"# #314 ORB-entry replay — DRY RUN (synthetic fixtures only; no real input opened) ({date.today().isoformat()})")
    say(f"- modules: orb_replay.py {X.sha_or_absent(os.path.abspath(__file__))[:16]} orb_goldens.py {X.sha_or_absent(G.__file__)[:16]} "
        f"ps_common.py {X.sha_or_absent(P.f('ps_common.py'))[:16]} ps_walk.py {X.sha_or_absent(P.f('ps_walk.py'))[:16]}")
    C = X.Claims(say)
    try:
        say("\n## The fixtures through walk_episode (the hand numbers of the registration's §8)")
        for (name, variant), exp in G.EXPECTED.items():
            o = run_fixture(name, G.FIXTURES[name], variant)
            for k, want in exp.items():
                got = o.get(k)
                if isinstance(want, (int, float)) and not isinstance(want, bool):
                    C(f"{name} {variant} {k}", want, got if got is not None else float("nan"), TOL)
                else:
                    C(f"{name} {variant} {k}", want, got)
        say("\n## Every fixture x every variant (printed; the registration names the expected rows above; o5h3x = the beside stop rule)")
        X.table(say, ["fixture", "variant", "status", "reason", "entry", "stop", "risk", "amb", "exit", "R", "held"],
                [[n, v, o["status"], o["reason"], _f(o["entry"]), _f(o["stop"]), _f(o["risk"]), _f(o["ambiguous_entry_bar"]), _f(o["exit"]), _f(o["r"]),
                  o["sessions_held"]] for n, fx in G.FIXTURES.items() for v in ALL_VARIANTS for o in [run_fixture(n, fx, v)]])
        say("\n## walk_episode on the review's adversarial cases (the refusal and exclusion paths the §8 table does not reach)")
        adversarial_claims(C)
        say("\n## The synthetic end-to-end trees through the --walk path (loaders, basis + shape checks, rule (c), the verdict functions)")
        synthetic_tree_walk(say, C)
        say("\n## The refusal trees (each must refuse, naming its reason; no result is written)")
        for label, kw, want in (("a doubled-price pull (basis_mismatch above REFUSE_SHARE)", {"scale": 2.0}, "basis_mismatch"),
                                ("a wrong-feed pull (the minute range inside the daily range: shape_mismatch above REFUSE_SHARE)", {"squeeze": 0.5}, "shape_mismatch"),
                                ("a sidecar declaring the wrong feed", {"meta": {"feed": "iex"}}, "sidecar feed"),
                                ("a minute row dated 2025-01-02", {"seal_row": True}, "the seal"),
                                ("a data pin that does not match", {"bad_pin": True}, "pinned")):
            try:
                synthetic_tree_walk(say, C, **kw)
                C(f"refusal tree: {label}", "refused", "ran")
            except GuardStop as ex:
                C(f"refusal tree: {label}", True, want in str(ex))
                say(f"    reason: {str(ex)[:220]}")
        say("\n## The exclusion trees (the walk runs; the episode is counted, never silently dropped)")
        synthetic_tree_walk(say, C, split=True)
        synthetic_tree_walk(say, C, delisted=True)
    except GuardStop as ex:
        say(f"\nDRY RUN STOPPED: {ex}")
        say(C.result())
        say.write(P.dry)
        return 2
    say("")
    say(C.result())
    if any(not r[3] for r in C.rows):
        say("DRY RUN FAILED")
        say.write(P.dry)
        return 2
    say("DRY RUN COMPLETE")
    say.write(P.dry)
    return 0


def adversarial_claims(C) -> None:
    """The reviewer's cases (scratch adv.py, 11-01) as claims: an early close cuts the 13:00+ prints; a hole with the position open; an
    entry on the last bar of a 1-session hold; rule (c) on an overlapping company; a 2025 minute row refuses at the loader."""
    S = list(G.SESSIONS)
    orb = G.WIN_S1[:5]
    # an early close: S2 = 2020-11-27 (13:00 close); its 15:59 bar is an after-hours print and the 12:59 close is the time exit (hold 2)
    S2 = ["2020-11-25", "2020-11-27", "2020-11-30"]
    mm = {S2[0]: bars_from_fixture(orb + [("09:40", 10.05, 10.10, 9.70, 9.75), ("15:59", 9.5, 9.5, 9.5, 9.5)]),
          S2[1]: bars_from_fixture([("09:30", 9, 9, 9, 9), ("12:59", 9, 9, 9, 9), ("15:59", 12, 12, 12, 12)]), S2[2]: bars_from_fixture([("15:59", 8, 8, 8, 8)])}
    o = walk_episode(S2, mm, lambda s: "bar", 5, 2)
    C("early close: the 12:59 bar is the 2-session time exit (the 15:59 print dropped)", "12:59", o["exit_ts"])
    C("early close: R = (9.79 - 9.00) / 0.92", 0.858695652173913, o["r"], TOL)
    # a hole on S2 with the position open
    mm = {S[0]: bars_from_fixture(orb + [("09:40", 10.05, 10.10, 9.70, 9.75)]), S[1]: None, S[2]: None}
    o = walk_episode(S, mm, lambda s: "hole" if s == S[1] else "bar", 5, 3)
    C("hole with the position open -> hole_open", "hole_open", o["status"])
    # a hole before the entry (S1 itself a hole)
    o = walk_episode(S, mm, lambda s: "hole" if s == S[0] else "bar", 5, 3)
    C("hole on the entry session -> hole (nothing opened)", "hole", o["status"])
    # the series ends before the entry session
    o = walk_episode(S, mm, lambda s: "ended", 5, 3)
    C("series ended before the entry session -> ended_before_entry", "ended_before_entry", o["status"])
    # entered on the last bar of a 1-session hold: the time exit is that bar's close
    mm = {S[0]: bars_from_fixture(orb + [("15:59", 10.0, 10.1, 9.0, 9.1)]), S[1]: None, S[2]: None}
    o = walk_episode(S, mm, lambda s: "bar", 5, 1)
    C("entry on the last bar, hold 1: time exit at that close, R = (9.79 - 9.10) / 0.92", 0.75, o["r"], TOL)
    # rule (c): three climaxes of one company; the second opens while the first is open; the third is free
    eps = [{"d0": "2023-07-03", "ticker": "X", "company_key": "k", "s1": "2023-07-05", f"{PRIMARY}_status": "settled", f"{PRIMARY}_exit_session": "2023-07-07"},
           {"d0": "2023-07-05", "ticker": "X", "company_key": "k", "s1": "2023-07-06", f"{PRIMARY}_status": "settled", f"{PRIMARY}_exit_session": "2023-07-10"},
           {"d0": "2023-07-07", "ticker": "X", "company_key": "k", "s1": "2023-07-10", f"{PRIMARY}_status": "untriggered", f"{PRIMARY}_exit_session": ""}]
    tally = apply_rule_c(eps, PRIMARY)
    C("rule (c): the overlapping second climax is episode_already_open", ["admitted", "episode_already_open", "admitted"], [e["decision"] for e in eps])
    C("rule (c): tally", {"admitted": 2, "episode_already_open": 1}, dict(tally))
    check_rule_c(eps, PRIMARY)
    C("rule (c): no two admitted episodes of one company key overlap (the §7 assert runs)", True, True)
    # a 2025 minute row refuses at the loader
    tmp = tempfile.mkdtemp(prefix="orb314_seal_", dir=os.environ.get("ORB314_SCRATCH") or None)
    pth = os.path.join(tmp, "m.csv.gz")
    with gzip.open(pth, "wt") as fh:
        fh.write("ticker,session_date,ts_et,open,high,low,close,volume\nZZZ,2025-01-02,09:30,1,1,1,1,1\n")
    try:
        load_minute_file(pth, {("ZZZ", "2025-01-02")})
        C("a minute row dated 2025-01-02 refuses at the loader", "refused", "loaded")
    except GuardStop as ex:
        C("a minute row dated 2025-01-02 refuses at the loader", True, "the seal" in str(ex))
    # a duplicate minute refuses
    try:
        rth([(570, 1, 1, 1, 1), (570, 1, 1, 1, 1)], S[0])
        C("a duplicate (ticker, session, minute) refuses", "refused", "loaded")
    except GuardStop as ex:
        C("a duplicate (ticker, session, minute) refuses", True, "duplicate" in str(ex))


def _f(x) -> str:
    return "" if x is None else (f"{x:.6f}" if isinstance(x, float) else str(x))


def synthetic_tree_walk(say, C, scale: float = 1.0, squeeze: float = 1.0, meta: dict = None, seal_row: bool = False, bad_pin: bool = False,
                        split: bool = False, delisted: bool = False) -> int:
    """Writes a tiny tree (two climax rows, one per era, on the fixture bars) in a temp dir and runs `walk()` on it with the pins
    overridden. Clean: the primary R of the era-B row equals fixture #1's; an unrequested session is counted minute_missing. The
    knobs build the refusal / exclusion trees: `scale` multiplies the MINUTE prices (basis_mismatch); `squeeze` pulls the minute highs
    and lows toward the close (a wrong feed: shape_mismatch); `meta` overrides sidecar keys; `seal_row` adds a 2025 minute row;
    `bad_pin` corrupts one data pin; `split` books a split inside BBB's walk; `delisted` sets BBB's owner delisted at D0+2."""
    scratch = os.environ.get("ORB314_SCRATCH") or None          # the session scratchpad when set; never the data tree
    if scratch:
        os.makedirs(scratch, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="orb314_", dir=scratch)
    data = os.path.join(tmp, "data")
    here = os.path.join(tmp, "here")
    os.makedirs(f"{data}/ps314"); os.makedirs(f"{data}/cb702_pre_v2"); os.makedirs(f"{data}/cb702"); os.makedirs(here)
    # calendars: era A = weekdays of 2019-06, era B = weekdays of 2023-07 (the fixture dates)
    calA = _weekdays("2019-06-03", 25)
    calB = _weekdays("2023-07-03", 25)
    Path(f"{data}/cb702_pre_v2/sessions.txt").write_text("\n".join(calA) + "\n")
    d0A, d0B = calA[1], "2023-07-03"            # era B: D0 = 07-03, D0+1..+3 = 07-05, 07-06, 07-07 (07-04 is a holiday: not in calB)
    calB = [d for d in calB if d != "2023-07-04"]
    Path(f"{data}/ps314/calendar_B.txt").write_text("\n".join(calB) + "\n")
    sA = calA[2:5]
    sB = ["2023-07-05", "2023-07-06", "2023-07-07"]
    assert [calB[calB.index(d0B) + k] for k in (1, 2, 3)] == sB
    # daily exports (headerless ticker,date,o,h,l,c,v): SPY on every session, the two names with bars around their walks. The walked
    # sessions' daily OHLC = fixture #1's session OHLC (so a clean minute file passes the basis and shape checks exactly).
    fx1 = G.FIXTURES["1_win_time_exit"]["minutes"]

    def sess_ohlc(bars):
        return (bars[0][1], max(b[2] for b in bars), min(b[3] for b in bars), bars[-1][4])
    s_ohlc = [sess_ohlc(fx1[s]) for s in G.SESSIONS]

    def daily_rows(t, cal_, d0, sess):
        rows = [(t, d, 10.0, 10.5, 9.5, 10.0, 1e6) for d in cal_ if d <= d0]
        rows += [(t, d, o, h, l, c, 1e6) for d, (o, h, l, c) in zip(sess, s_ohlc)]
        return rows
    rowsA = [("SPY", d, 100.0, 101.0, 99.0, 100.0, 1e6) for d in calA] + daily_rows("AAA", calA, d0A, sA)
    rowsB = [("SPY", d, 100.0, 101.0, 99.0, 100.0, 1e6) for d in calB] + daily_rows("BBB", calB, d0B, sB)
    for path, rows in ((f"{data}/cb702_pre_v2/daily_closes_all.csv.gz", rowsA), (f"{data}/cb702/daily_closes_all.csv.gz", rowsB)):
        with gzip.open(path, "wt") as fh:
            for r in rows:
                fh.write(",".join(str(x) for x in r) + "\n")
    with gzip.open(f"{data}/cb702_pre_v2/daily_raw_close.csv.gz", "wt") as fh:
        for r in rowsA:
            fh.write(f"{r[0]},{r[1]},{r[5]}\n")
    Path(f"{data}/cb702/cb702_splits.psv").write_text("ZZZ|2023-01-03|1|2\n" + ("BBB|2023-07-06|1|10\n" if split else ""))
    cols = ["ticker", "d0", "era", "population", "company_key", "void_adjustment_event", "open_at_seal", "owner_delisted"]
    od = "2023-07-05" if delisted else "active"
    cl = [("AAA", d0A, "A", "P1", "cik:1", "0", "0", ""), ("BBB", d0B, "B", "P2", "cik:2", "0", "0", od), ("BBB", d0B, "B", "P2small", "cik:2", "0", "0", od)]
    X.write_tsv(f"{data}/ps314/climax_list.tsv", cols, [dict(zip(cols, r)) for r in cl])
    ecols = ["ticker", "d0", "population", "adr20", "distribution_class"]
    X.write_tsv(f"{data}/ps314/episodes.tsv", ecols, [{"ticker": t, "d0": d, "population": p, "adr20": "0.10", "distribution_class": ""}
                                                       for t, d, _, p, *_ in cl])
    # the minute file: BBB on all three sessions (fixture #1); AAA on sessions 1 and 3 only (session 2 missing -> minute_missing_open)
    with gzip.open(os.path.join(here, "minute_bars.csv.gz"), "wt") as fh:
        fh.write("ticker,session_date,ts_et,open,high,low,close,volume\n")
        for t, sess, keep in (("BBB", sB, (0, 1, 2)), ("AAA", sA, (0, 2))):
            for k in keep:
                f = scale * (10.0 if (split and t == "BBB" and sess[k] < "2023-07-06") else 1.0)   # the split tree: pre-split RAW prints are 10x
                for ts, o, h, l, c in fx1[G.SESSIONS[k]]:
                    h2, l2 = c + (h - c) * squeeze, c - (c - l) * squeeze
                    fh.write(f"{t},{sess[k]},{ts},{o * f},{h2 * f},{l2 * f},{c * f},1000\n")
        if seal_row:
            fh.write("BBB,2025-01-02,09:30,1,1,1,1,1\n")
    P = Paths(data=data, here=here, doc=DOC, pins={})
    for k in REQUEST_PIN_KEYS + ("episodes", "export_A", "raw_A", "export_B", "splits_B"):
        P.pins[k] = X.sha(P.f(k))
    if bad_pin:
        P.pins["export_B"] = "0" * 64
    write_request(P, quiet=True)
    m = {**META_REQUIRED, "request_sha256": X.sha(P.request), "source": "synthetic tree"}
    m.update(meta or {})
    json.dump(m, open(P.minute_meta, "w"))
    res = walk(P, say=_Quiet(), freeze=False, write=False)
    eps = res["episodes"]
    bbb = [e for e in eps if e["ticker"] == "BBB" and e["population"] == "P2"][0]
    aaa = [e for e in eps if e["ticker"] == "AAA"][0]
    tag = "split tree" if split else "delisted tree" if delisted else "clean tree"
    if split:
        C(f"{tag}: a split executing inside BBB's walk -> split_in_walk (counted)", "split_in_walk", bbb[f"{PRIMARY}_status"])
    elif delisted:
        C(f"{tag}: BBB's owner delisted at D0+2 -> ended_mid_walk (booked at the last close, then the haircut)", "ended_mid_walk", bbb[f"{PRIMARY}_status"])
        C(f"{tag}: BBB r_last_close = (9.79 - 9.00) / 0.92", 0.858695652173913, bbb[f"{PRIMARY}_r_last_close"], TOL)
    else:
        C(f"{tag}: BBB (era B) primary R == fixture #1", G.EXPECTED[("1_win_time_exit", "o5h3")]["r"], bbb[f"{PRIMARY}_r"], TOL)
        C(f"{tag}: BBB basis + shape checks passed (status settled)", "settled", bbb[f"{PRIMARY}_status"])
        C(f"{tag}: BBB beside rule (o5h3x) R == the primary's here (the entry bar's high is under the prior high)",
          G.EXPECTED[("1_win_time_exit", "o5h3")]["r"], bbb[f"{BESIDE}_r"], TOL)
        C(f"{tag}: sessions checked against the daily OHLC", 5, res["n_checked"])
        C(f"{tag}: basis + shape failures", 0, res["n_fail"])
        C(f"{tag}: request rows == 6 (2 names x 3 sessions)", 6, res["n_request"])
    C(f"{tag}: AAA (era A) session 2 absent -> minute_missing_open", "minute_missing_open", aaa[f"{PRIMARY}_status"])
    C(f"{tag}: rule (c) admits both deciding rows", 2, sum(1 for e in eps if e["decision"] == "admitted" and e["population"] in ("P1", "P2")))
    say(f"  {tag} at {tmp}: {len(eps)} climax rows walked; printout lines {len(res['lines'])}")
    return 0


class _Quiet:
    def __init__(self): self.lines = []
    def __call__(self, msg=""): self.lines.append(msg)
    def write(self, path): pass


def _weekdays(start: str, n: int) -> list:
    from datetime import timedelta
    d, out = date.fromisoformat(start), []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the population and the request (§1, §2, §6)
# ═════════════════════════════════════════════════════════════════════════════════════════════
def load_calendars(P: Paths) -> dict:
    cal = {}
    for era, key in (("A", "sessions_A"), ("B", "calendar_B")):
        cal[era] = [ln.strip() for ln in open(P.f(key)) if ln.strip()]
        assert all(a < b for a, b in zip(cal[era], cal[era][1:])), f"calendar {era} not ascending"
    return cal


def climax_rows(P: Paths, cal: dict) -> list:
    """The pinned climax list with the walk sessions derived from the era's calendar; `walkable` by the 3-session seal rule."""
    rows = X.read_tsv(P.f("climax_list"))
    for r in rows:
        c = cal[r["era"]]
        import bisect
        i = bisect.bisect_left(c, r["d0"])
        if i >= len(c) or c[i] != r["d0"]:
            raise GuardStop(f"climax {r['ticker']} {r['d0']}: D0 is not a session of calendar {r['era']}")
        ss = [c[i + k] if i + k < len(c) else None for k in (1, 2, 3)]
        r["s1"], r["s2"], r["s3"] = ss
        r["walkable"] = ss[2] is not None and ss[2] <= SEAL
    return rows


def pre_walk_filter(rows: list, episodes: dict) -> None:
    """Sets `prewalk` = '' (in) or the exclusion name (the 10-28 exclusions as pinned)."""
    for r in rows:
        e = episodes.get((r["ticker"], r["d0"], r["population"]), {})
        if not r["walkable"]:
            r["prewalk"] = "open_at_seal"
        elif str(r.get("void_adjustment_event", "0")) == "1":
            r["prewalk"] = "void_adjustment_event"
        elif e.get("distribution_class") == "distribution":
            r["prewalk"] = "distribution"
        else:
            r["prewalk"] = ""
        r["adr20"] = e.get("adr20", "")


def request_rows(rows: list) -> list:
    why = defaultdict(list)
    for r in rows:
        if not r["walkable"]:
            continue
        for k in (1, 2, 3):
            why[(r["ticker"], r[f"s{k}"])].append(f"{r['population']} D0={r['d0']} s{k}")
    out = []
    for (t, s), w in sorted(why.items()):
        if s >= SEAL_FIRST:
            raise GuardStop(f"request: {t} {s} is on or after {SEAL_FIRST} (the seal)")
        out.append({"ticker": t, "session_date": s, "why": "; ".join(sorted(set(w)))})
    return out


def write_request(P: Paths, quiet: bool = False) -> int:
    probs = pin_problems(P, REQUEST_PIN_KEYS)
    if probs:
        raise GuardStop("request refused, pins: " + "; ".join(probs))
    if os.path.exists(P.request):
        raise GuardStop(f"request refused: {P.request} exists (delete it by hand to re-derive)")
    cal = load_calendars(P)
    rows = climax_rows(P, cal)
    req = request_rows(rows)
    X.write_tsv(P.request, ["ticker", "session_date", "why"], req)
    if not quiet:
        n_walk = sum(1 for r in rows if r["walkable"])
        print(f"minute_request.tsv: {len(req)} (ticker, session) rows, {len({r['ticker'] for r in req})} tickers, "
              f"sessions {min(r['session_date'] for r in req)}..{max(r['session_date'] for r in req)}; climax rows walkable {n_walk} of {len(rows)} "
              f"({len({(r['ticker'], r['d0']) for r in rows if r['walkable']})} distinct (ticker, D0))")
    return len(req)


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the daily context (the frozen exports through the 10-28 loaders) — the basis + shape checks, holes, series ends, splits in the walk
# ═════════════════════════════════════════════════════════════════════════════════════════════
class DailyCtx:
    def __init__(self, P: Paths, tickers_A: set, tickers_B: set, say):
        self.series = {}          # (era, ticker) -> {"dates", "close", "raw" (close), "factor", "raw_o", "raw_h", "raw_l"}
        self.era_last = {"A": X.A_LAST, "B": SEAL}
        if tickers_A:
            D, info = X.load_daily_subset(P.f("export_A"), keep=tickers_A, cut=X.A_LAST)
            say(f"  era A export: rows read {info['rows_read']}, kept {info['rows_kept']} for {len(tickers_A)} tickers (cut {X.A_LAST})")
            raw, rinfo = X.load_raw_close_subset(P.f("raw_A"), keep=tickers_A, cut=X.A_LAST)
            say(f"  era A raw close: rows read {rinfo['rows_read']}, kept {rinfo['rows_kept']}")
            for t in tickers_A:
                if t not in D.tid:
                    continue
                k = D.tid[t]
                sl = slice(D.start[k], D.stop[k])
                ds = [D.cal[i].isoformat() for i in D.ci[sl]]
                cl = D.c[sl].astype(float)
                rd, rc = raw.get(t, ([], np.zeros(0)))
                rmap = dict(zip(rd, rc))
                rr = np.array([rmap.get(d, np.nan) for d in ds], dtype=float)
                fac = rr / cl                                   # era A: raw = adjusted x (raw close / adjusted close), per bar
                self.series[("A", t)] = {"dates": ds, "close": cl, "raw": rr, "factor": fac, "raw_o": D.o[sl].astype(float) * fac,
                                         "raw_h": D.h[sl].astype(float) * fac, "raw_l": D.l[sl].astype(float) * fac}
        if tickers_B:
            D, info = X.load_daily_subset(P.f("export_B"), keep=tickers_B, cut=SEAL)
            say(f"  era B export: rows read {info['rows_read']}, kept {info['rows_kept']} for {len(tickers_B)} tickers (cut {SEAL})")
            splits = X.load_splits(Path(P.f("splits_B")), through=date.fromisoformat(X.SPLITS_THROUGH))
            self.splits_B = splits
            for t in tickers_B:
                if t not in D.tid:
                    continue
                k = D.tid[t]
                sl = slice(D.start[k], D.stop[k])
                ds = [D.cal[i].isoformat() for i in D.ci[sl]]
                cl = D.c[sl].astype(float)
                # era B: raw = adjusted x the product of the splits executing after the bar (date objects: the first draft passed ISO strings,
                # which raised on the first ticker WITH a split — found by the split tree of the dry run, 11-01)
                fac = X.factor_by_bar([date.fromisoformat(d) for d in ds], splits.get(t, []))
                self.series[("B", t)] = {"dates": ds, "close": cl, "raw": cl * fac, "factor": fac, "raw_o": D.o[sl].astype(float) * fac,
                                         "raw_h": D.h[sl].astype(float) * fac, "raw_l": D.l[sl].astype(float) * fac}
        else:
            self.splits_B = {}

    def state(self, era: str, t: str, s: str, owner_delisted: str) -> str:
        sr = self.series.get((era, t))
        if sr is None:
            return "ended"
        if era == "B" and owner_delisted and owner_delisted[:1].isdigit() and s > owner_delisted:
            return "ended"
        if s in sr["_set"]:
            return "bar"
        if s > sr["dates"][-1]:
            return "ended"
        return "hole"

    def finish(self):
        for sr in self.series.values():
            sr["_set"] = set(sr["dates"])
            sr["_idx"] = {d: i for i, d in enumerate(sr["dates"])}

    def raw_ohlc(self, era, t, s) -> tuple:
        sr = self.series[(era, t)]
        i = sr["_idx"][s]
        return float(sr["raw_o"][i]), float(sr["raw_h"][i]), float(sr["raw_l"][i]), float(sr["raw"][i])

    def split_in_walk(self, era, t, d0, s3) -> bool:
        if era == "B":
            return any(d0 < ex.isoformat() <= s3 for ex, _ in self.splits_B.get(t, []))
        sr = self.series[(era, t)]
        i0 = sr["_idx"].get(d0)
        later = [i for d, i in sr["_idx"].items() if d0 < d <= s3]
        if i0 is None or not later:
            return False
        f0, f1 = sr["factor"][i0], sr["factor"][max(later)]
        if not (np.isfinite(f0) and np.isfinite(f1)):
            return False
        return abs(f1 / f0 - 1.0) > X.JUMP_FAC_CHANGE

    def closes_through(self, era, t, s) -> tuple:
        """(the daily closes through session s, the raw close at s) for ending_class."""
        sr = self.series[(era, t)]
        i = sr["_idx"][s]
        return list(sr["close"][: i + 1]), float(sr["raw"][i])


def session_check(bars: list, raw_ohlc: tuple) -> tuple:
    """The pull's own check on one session: (verdict, ratios). verdict = '' | 'basis_mismatch' | 'shape_mismatch'.
    basis: the minute RTH low / the daily RAW low inside BASIS_BAND (a wrong symbol, year or basis prints a different level);
    shape: the minute RTH high / daily RAW high AND low / low each inside SHAPE_BAND (a thinner feed or a shifted clock prints a
    narrower or displaced range while the level can still pass). The open and close are printed as diagnostics, never a verdict
    (the official close is the 16:00 auction print, not the 15:59 bar; calibrated 11-01 on 715 local (ticker, session) pairs)."""
    ro, rh, rl, rc = raw_ohlc
    mo, mh, ml, mc = bars[0][1], max(b[2] for b in bars), min(b[3] for b in bars), bars[-1][4]
    if not all(v > 0 and math.isfinite(v) for v in (ro, rh, rl, rc)):
        return "basis_mismatch", {}
    ratios = {"low": ml / rl, "high": mh / rh, "open": mo / ro, "close": mc / rc}
    if not (BASIS_BAND[0] <= ratios["low"] <= BASIS_BAND[1]):
        return "basis_mismatch", ratios
    if not (SHAPE_BAND[0] <= ratios["high"] <= SHAPE_BAND[1] and SHAPE_BAND[0] <= ratios["low"] <= SHAPE_BAND[1]):
        return "shape_mismatch", ratios
    return "", ratios


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the walk (§1-§5)
# ═════════════════════════════════════════════════════════════════════════════════════════════
HEX64 = re.compile(r"\b[0-9a-f]{64}\b")


def doc_pins_above_marker(doc: str) -> dict:
    """The code pins written ABOVE the doc's marker: the first 64-hex on a line that names the key in a `| key |` table cell."""
    raw = open(doc, "rb").read()
    sp = X.C.marker_spans(raw)
    body = (raw[:sp[0][0]] if len(sp) == 1 else raw).decode("utf-8", errors="replace")
    out = {}
    for ln in body.splitlines():
        for k in CODE_PIN_KEYS:
            if f"| {k} |" in ln:
                m = HEX64.search(ln)
                if m:
                    out[k] = m.group(0)
    return out


def freeze_problems(P: Paths) -> list:
    """The two-stage freeze. ABOVE the marker (the pre-pull commit): the sha256 of this file, the goldens, the request and the dry run,
    each equal to the file on disk. BELOW the marker (pasted by the main loop): `freeze_commit` (the commit that carried the above;
    the committed copies of the four files and of the doc body must equal what is on disk), `doc_body`, `minute_bars`, `minute_bars_meta`."""
    if not os.path.exists(P.doc):
        return ["the registration is missing"]
    out = []
    above = doc_pins_above_marker(P.doc)
    now = P.code_pins()
    for k in CODE_PIN_KEYS:
        if k not in above:
            out.append(f"{k}: no pin above the doc's marker")
        elif above[k] != now[k]:
            out.append(f"{k}: on disk {now[k][:16]} != pinned above the marker {above[k][:16]}")
    below = {"doc_body": X.doc_body_sha(P.doc), "minute_bars": X.sha_or_absent(P.minute_bars), "minute_bars_meta": X.sha_or_absent(P.minute_meta)}
    miss = X.freeze_missing(P.doc, below)
    out += [f"{k} = {below[k][:16]}… not pinned under the doc's <!-- FREEZE --> line" for k in miss]
    commit = freeze_commit_of(P.doc)
    if commit is None:
        out.append("freeze_commit = <hash> is not under the doc's <!-- FREEZE --> line (the pre-pull commit)")
    else:
        out += committed_copy_problems(commit, now, below["doc_body"])
    return out


def freeze_commit_of(doc: str):
    raw = open(doc, "rb").read()
    sp = X.C.marker_spans(raw)
    if len(sp) != 1:
        return None
    tail = raw[sp[0][1]:].decode("utf-8", errors="replace")
    m = re.search(r"freeze_commit\s*[=:|]\s*`?([0-9a-f]{7,40})`?", tail)
    return m.group(1) if m else None


def committed_copy_problems(commit: str, now: dict, doc_body_now: str) -> list:
    """`git cat-file` (local, no network) of the four code files and the doc at `commit`: each must hash to what is on disk now."""
    out = []
    for k, path in GIT_PATHS.items():
        try:
            blob = subprocess.run(["git", "-C", REPO, "cat-file", "-p", f"{commit}:{path}"], capture_output=True, check=True).stdout
        except (subprocess.CalledProcessError, FileNotFoundError) as ex:
            out.append(f"freeze_commit {commit[:12]}: {path} cannot be read from the commit ({getattr(ex, 'stderr', b'')[:80]!r})")
            continue
        if k == "doc":
            sp = X.C.marker_spans(blob)
            got = hashlib.sha256(blob[:sp[0][0]] if len(sp) == 1 else blob).hexdigest()
            if got != doc_body_now:
                out.append(f"freeze_commit {commit[:12]}: the committed doc body {got[:16]} != the doc body on disk {doc_body_now[:16]}")
        else:
            got = hashlib.sha256(blob).hexdigest()
            if got != now[k]:
                out.append(f"freeze_commit {commit[:12]}: committed {k} {got[:16]} != on disk {now[k][:16]}")
    return out


def gate_walk(P: Paths, freeze: bool) -> list:
    probs = pin_problems(P)
    if freeze:
        probs += freeze_problems(P)
        if not X.printout_ends(P.dry, "DRY RUN COMPLETE"):
            probs.append("dry_run.txt does not end DRY RUN COMPLETE (run --dry-run first)")
    if os.path.exists(P.result):
        probs.append(f"{P.result} exists: the walk runs once")
    if not os.path.exists(P.minute_bars):
        probs.append(f"{P.minute_bars} is absent (the main loop's pull)")
    if not os.path.exists(P.request):
        probs.append(f"{P.request} is absent (run --request first)")
    else:
        probs += meta_problems(P.minute_meta, X.sha(P.request))
    return probs


def closes_on(ep: dict, v: str) -> str:
    st = ep[f"{v}_status"]
    if st == "settled":
        return ep[f"{v}_exit_session"]
    if st in ("ended_mid_walk", "hole_open", "minute_missing_open"):
        return ep[f"{v}_last_session"] or ep["s1"]
    return ep["s1"]                                   # nothing was opened: free from the entry session on


def apply_rule_c(eps: list, v: str) -> Counter:
    """The 10-28 rule (c), re-applied: one open episode per company key, D0 order, advance-before-decide (an earlier episode closing
    on D0 has closed by that night's bar)."""
    eps.sort(key=lambda e: (e["d0"], e["ticker"]))
    open_until, tally = {}, Counter()
    for e in eps:
        k = e["company_key"]
        until = open_until.get(k)
        if until is not None and until > e["d0"]:
            e["decision"] = "episode_already_open"
            tally["episode_already_open"] += 1
            continue
        e["decision"] = "admitted"
        tally["admitted"] += 1
        open_until[k] = closes_on(e, v)
    return tally


def check_rule_c(eps: list, v: str) -> None:
    """§7 WOULD-FAIL-IF: no two admitted episodes of one company key are open on one night (each closes on or before the next's D0)."""
    by_key = defaultdict(list)
    for e in eps:
        if e.get("decision") == "admitted":
            by_key[e["company_key"]].append(e)
    for k, lst in by_key.items():
        lst.sort(key=lambda e: e["d0"])
        for a, b in zip(lst, lst[1:]):
            if closes_on(a, v) > b["d0"]:
                raise GuardStop(f"rule (c): two admitted episodes of {k} open on one night ({a['ticker']} {a['d0']} closes {closes_on(a, v)} > {b['d0']})")


def check_episode(e: dict) -> None:
    """The registration's §7 WOULD-FAIL-IF, per variant: a settled entry on D0+1 only, the exit inside the hold, a stop booked on the
    entry bar only at the stop price with the bar flagged ambiguous, R equal to (entry - exit) / (stop - entry) recomputed from the
    booked prices, no settled row behind a basis / shape / split exclusion."""
    for v in ALL_VARIANTS:
        if e[f"{v}_status"] != "settled":
            continue
        if e.get("pre"):
            raise GuardStop(f"{e['ticker']} {e['d0']} {v}: settled behind the exclusion {e['pre']}")
        _, hold, _ = parse_variant(v)
        if e[f"{v}_entry_session"] != e["s1"]:
            raise GuardStop(f"{e['ticker']} {e['d0']} {v}: entry session {e[f'{v}_entry_session']} != D0+1 {e['s1']}")
        if e[f"{v}_exit_session"] not in [e["s1"], e["s2"], e["s3"]][:hold]:
            raise GuardStop(f"{e['ticker']} {e['d0']} {v}: exit session {e[f'{v}_exit_session']} outside the {hold}-session hold")
        on_entry_bar = e[f"{v}_exit_session"] == e[f"{v}_entry_session"] and e[f"{v}_exit_ts"] == e[f"{v}_entry_ts"]
        if on_entry_bar and e[f"{v}_reason"] == "stop" and not (e[f"{v}_exit"] == e[f"{v}_stop"] and e[f"{v}_ambiguous_entry_bar"] == 1):
            raise GuardStop(f"{e['ticker']} {e['d0']} {v}: a stop on the entry bar not at the stop price or not flagged ambiguous")
        back = (e[f"{v}_entry"] - e[f"{v}_exit"]) / (e[f"{v}_stop"] - e[f"{v}_entry"])
        if abs(back - e[f"{v}_r"]) > 1e-9:
            raise GuardStop(f"{e['ticker']} {e['d0']} {v}: R {e[f'{v}_r']} != recomputed {back}")


def as_1028_row(e: dict, v: str) -> dict:
    """The fields ps_walk.base_verdict / verdict_three_ways read, from this walk's columns (the 10-28 names, so ONE function judges both)."""
    return {"company_key": e["company_key"], "r5_entry_month": e["s1"][:7], "r5_r": e[f"{v}_r"], "r5_pnl_adr": e[f"{v}_pnl_adr"],
            "r5_r_slip1": e[f"{v}_r_slip1"], "r5_r_slip2": e[f"{v}_r_slip2"], "r5_pnl_adr_slip1": e[f"{v}_pnl_adr_slip1"],
            "r5_pnl_adr_slip2": e[f"{v}_pnl_adr_slip2"], "r5_r_tick1": e[f"{v}_r_tick1"], "r5_r_tick2": e[f"{v}_r_tick2"],
            "r5_r_tick5": e[f"{v}_r_tick5"], "r5_pnl_adr_tick1": e[f"{v}_pnl_adr_tick1"], "r5_pnl_adr_tick2": e[f"{v}_pnl_adr_tick2"],
            "r5_pnl_adr_tick5": e[f"{v}_pnl_adr_tick5"], "r5_r_last_close": e[f"{v}_r_last_close"], "r5_r_haircut": e[f"{v}_r_haircut"],
            "r5_pnl_adr_last_close": e[f"{v}_pnl_adr_last_close"], "r5_pnl_adr_haircut": e[f"{v}_pnl_adr_haircut"], "ticker": e["ticker"], "d0": e["d0"]}


def walk(P: Paths, say=None, freeze: bool = True, write: bool = True) -> dict:
    say = say or X.Say()
    say(f"# #314 ORB-entry replay — THE WALK (run once) ({date.today().isoformat()})")
    say("Guards: no network, no DB, no production server, nothing dated 2025-01-01 or later read from any bar file; the 10-28 helpers imported, never copied.")
    say(f"- modules: orb_replay.py {X.sha(os.path.abspath(__file__))[:16]} orb_goldens.py {X.sha(G.__file__)[:16]} "
        f"ps_common.py {X.sha_or_absent(P.f('ps_common.py'))[:16]} ps_walk.py {X.sha_or_absent(P.f('ps_walk.py'))[:16]}")
    probs = gate_walk(P, freeze)
    if probs:
        raise GuardStop("walk refused: " + "; ".join(probs))
    say(f"- minute file {X.sha(P.minute_bars)[:16]}; sidecar {json.load(open(P.minute_meta))}; request {X.sha(P.request)[:16]}; "
        f"climax list {X.sha(P.f('climax_list'))[:16]}")
    cal = load_calendars(P)
    rows = climax_rows(P, cal)
    episodes = {(e["ticker"], e["d0"], e["population"]): e for e in X.read_tsv(P.f("episodes"))}
    pre_walk_filter(rows, episodes)
    req = X.read_tsv(P.request)
    derived = {(r["ticker"], r["session_date"]) for r in request_rows(rows)}
    if {(r["ticker"], r["session_date"]) for r in req} != derived:
        raise GuardStop("the request file's (ticker, session) set differs from the set derived from the pinned climax list")
    say(f"\n## The population (the pinned climax list, the 10-28 exclusions re-applied; §1)")
    for pop in POPS:
        sub = [r for r in rows if r["population"] == pop]
        c = Counter(r["prewalk"] or "pre-walk population" for r in sub)
        inn = [r for r in sub if not r["prewalk"]]
        say(f"  {pop}: climax rows {len(sub)} -> {dict(c)}; pre-walk population {len(inn)} (A {sum(1 for r in inn if r['era'] == 'A')}, "
            f"B {sum(1 for r in inn if r['era'] == 'B')}), companies {len({r['company_key'] for r in inn})}")
    walkrows = [r for r in rows if not r["prewalk"]]
    pairs = {(r["ticker"], r[f"s{k}"]) for r in walkrows for k in (1, 2, 3)}
    say(f"\n## Loading (the frozen inputs only)")
    bars, info = load_minute_file(P.minute_bars, pairs)
    say(f"  minute file: rows read {info['rows_read']}, wanted {info['rows_wanted']}, (ticker, session) pairs present {info['pairs']} of {len(pairs)}")
    ctx = DailyCtx(P, {r["ticker"] for r in walkrows if r["era"] == "A"}, {r["ticker"] for r in walkrows if r["era"] == "B"}, say)
    ctx.finish()
    # ---- the pull's own check, every walked session present: basis + shape against the daily RAW OHLC; above REFUSE_SHARE the run refuses ----
    say(f"\n## The pull's check (§6): minute RTH low / daily raw low in [{BASIS_BAND[0]}, {BASIS_BAND[1]}] (basis); high / high and low / low "
        f"each in [{SHAPE_BAND[0]}, {SHAPE_BAND[1]}] (shape); more than {REFUSE_SHARE:.0%} of the sessions checked outside -> the run refuses")
    era_of = {(r["ticker"], r[f"s{k}"]): r["era"] for r in walkrows for k in (1, 2, 3)}
    checked, fails, verdict_of, diag = 0, [], {}, defaultdict(list)
    for (t, s) in sorted(pairs):
        era = era_of[(t, s)]
        if (t, s) not in bars or ctx.state(era, t, s, "") != "bar":
            continue
        b = rth(bars[(t, s)], s)
        if not b:
            continue
        checked += 1
        v, ratios = session_check(b, ctx.raw_ohlc(era, t, s))
        for k, val in ratios.items():
            diag[k].append(val)
        if v:
            verdict_of[(t, s)] = v
            fails.append((t, s, v, {k: round(x, 4) for k, x in ratios.items()}))
    share = len(fails) / checked if checked else 0.0
    say(f"  sessions checked {checked}; basis_mismatch {sum(1 for f in fails if f[2] == 'basis_mismatch')}; shape_mismatch "
        f"{sum(1 for f in fails if f[2] == 'shape_mismatch')}; share {share:.4f}")
    for k in ("low", "high", "open", "close"):
        if diag[k]:
            q = np.quantile(diag[k], [0.005, 0.5, 0.995])
            say(f"  minute / daily raw {k}: p0.5 {q[0]:.4f} median {q[1]:.4f} p99.5 {q[2]:.4f} (n {len(diag[k])})")
    for f in fails[:40]:
        say(f"    {f}")
    if share > REFUSE_SHARE:
        raise GuardStop(f"the pull fails its own check: {len(fails)} of {checked} walked sessions outside the basis / shape bands "
                        f"({share:.2%} > {REFUSE_SHARE:.0%}); first: {fails[:5]}. Re-pull (feed sip, adjustment raw, tz ET); no result written")
    # ---- the walk, once per distinct (ticker, D0); every variant ----
    say(f"\n## The walk ({len(VARIANTS)} variants + the beside stop rule {BESIDE}; primary {PRIMARY})")
    results, split_fail, missing_list, excluded = {}, [], [], Counter()
    for r in walkrows:
        key = (r["ticker"], r["d0"])
        if key in results:
            continue
        t, era, ss = r["ticker"], r["era"], [r["s1"], r["s2"], r["s3"]]
        od = r.get("owner_delisted", "")
        state = lambda s, t=t, era=era, od=od: ctx.state(era, t, s, od)
        minutes = {s: bars.get((t, s)) for s in ss}
        pre = next((verdict_of[(t, s)] for s in ss if (t, s) in verdict_of), "")
        if not pre and state(ss[0]) == "bar" and ctx.split_in_walk(era, t, r["d0"], ss[2]):
            pre = "split_in_walk"
            split_fail.append((t, r["d0"]))
        if pre:
            excluded[pre] += 1
        out = {"pre": pre}
        for v in ALL_VARIANTS:
            orb, hold, rule = parse_variant(v)
            if pre:
                o = blank(); o.update(status=pre, reason=pre)
            else:
                o = walk_episode(ss, minutes, state, orb, hold, rule)
                if o["status"] == "ended_mid_walk":
                    closes, raw_last = ctx.closes_through(era, t, o["last_session"])
                    o = book_ended(o, closes, raw_last)
                if o["status"] in ("minute_missing", "minute_missing_open") and v == PRIMARY:
                    missing_list.append((t, r["d0"]))
            add_pnl(o, r["adr20"])
            for k2, val in o.items():
                out[f"{v}_{k2}"] = val
        results[key] = out
    eps = []
    for r in walkrows:
        e = {k: r[k] for k in ("ticker", "d0", "era", "population", "company_key", "s1", "s2", "s3", "adr20")}
        e.update(results[(r["ticker"], r["d0"])])
        check_episode(e)
        eps.append(e)
    say(f"  excluded at the walk (distinct (ticker, D0)): {dict(excluded)}")
    say(f"  split_in_walk: {len(split_fail)} {split_fail[:20]}")
    say(f"  minute_missing on the primary (ticker, D0): {len(missing_list)}" + (f" e.g. {missing_list[:30]}" if missing_list else ""))
    say("\n## Expectations fixed in the registration (§5; a miss is printed first and changes no rule) — the file-level ones")
    for era, cap in (("A", 0.25), ("B", 0.10)):
        want = [p for p in pairs if era_of[p] == era]
        miss = sum(1 for p in want if p not in bars)
        mshare = miss / len(want) if want else 0.0
        say(f"  [{'held' if mshare < cap else 'MISS'}] minute_missing share era {era} under {cap:.0%}: {mshare:.3f} ({miss} of {len(want)} (ticker, session) pairs)")
    say(f"  [{'held' if share < 0.02 else 'MISS'}] basis + shape mismatch under 2% of the sessions checked: {share:.4f} ({len(fails)} of {checked})")
    # ---- rule (c) once, from the primary ----
    nums = {}
    say(f"\n## Rule (c) — one open episode per company key, from the primary walk's close dates, reused by every variant")
    for pop in POPS:
        sub = [e for e in eps if e["population"] == pop]
        tally = apply_rule_c(sub, PRIMARY)
        check_rule_c(sub, PRIMARY)
        say(f"  {pop}: {dict(tally)}")
    # ---- the result per population ----
    say(f"\n## The base verdict (primary {PRIMARY}: 5-minute range, 3 sessions, stop = the high before the entry bar + 1c; n = settled, admitted by rule (c))")
    verdicts = {}
    for pop in POPS:
        allpop = [e for e in eps if e["population"] == pop]
        sub = [e for e in allpop if e["decision"] == "admitted"]
        st = Counter(e[f"{PRIMARY}_status"] for e in sub)
        say(f"\n### {pop}: pre-walk {len(allpop)}, admitted {len(sub)}; by status {dict(st)}")
        say(f"  10-28 primary beside: {BASELINE_1028[pop]}")
        trig_all = [e for e in allpop if e[f"{PRIMARY}_entry"] is not None]          # the share over the WHOLE pre-walk population (before rule (c))
        share_t = len(trig_all) / len(allpop) if allpop else float("nan")
        for label, lo, hi in EXPECTATIONS:
            say(f"  [{'held' if lo <= share_t <= hi else 'MISS'}] {pop}: {label}: {share_t:.3f} ({len(trig_all)} of {len(allpop)})")
        trig = [e for e in sub if e[f"{PRIMARY}_entry"] is not None]
        if trig:
            rr = np.array([e[f"{PRIMARY}_risk"] / e[f"{PRIMARY}_entry"] for e in trig])
            med = float(np.median(rr))
            say(f"  risk / entry on the triggered (admitted): median {med:.3f}, quartiles {np.quantile(rr, .25):.3f} / {np.quantile(rr, .75):.3f} "
                f"(the 10-28 median 0.360)")
            say(f"  [{'held' if med < 0.15 else 'MISS'}] {pop}: median risk / entry under 15%: {med:.3f}")
            nv = sum(1 for e in trig if e[f"{PRIMARY}_status"] == "void_bad_geometry")
            say(f"  [{'held' if nv / len(trig) < 0.05 else 'MISS'}] {pop}: void_bad_geometry under 5% of the triggered: {nv} of {len(trig)}")
            amb = sum(1 for e in trig if e[f"{PRIMARY}_ambiguous_entry_bar"] == 1)
            say(f"  ambiguous entry bars (the entry bar's high reached the stop; booked -1R): {amb} of {len(trig)} triggered ({X.pct(amb, len(trig))})")
            nums[f"orb:{pop}:ambiguous_entry_bars"] = amb
        settled_all = [e for e in sub if e[f"{PRIMARY}_status"] == "settled"]
        if settled_all:
            wr = sum(1 for e in settled_all if e[f"{PRIMARY}_r"] > 0) / len(settled_all)
            say(f"  [{'held' if wr < 0.475 else 'MISS'}] {pop}: win rate under the 10-28's 47.5%: {wr:.3f}")
            n3 = sum(1 for e in settled_all if e[f"{PRIMARY}_r"] >= X.TAIL_R)
            if pop in DECIDING:
                say(f"  [{'held' if n3 >= 1 else 'MISS'}] {pop}: at least one settled short at >= 3R realized: {n3}")
        S = [as_1028_row(e, PRIMARY) for e in settled_all]
        for era in ("pooled", "A", "B"):
            SS = S if era == "pooled" else [x for x, e in zip(S, settled_all) if e["era"] == era]
            bv = W.base_verdict(SS, f"orb:{pop}:{era}")
            W._bv_numbers(f"orb:{pop}:{era}", bv, nums)
            W._bv_line(say, f"{pop} {era}", bv)
            if era == "pooled":
                verdicts[pop] = bv
                wins = sum(1 for x in SS if float(x["r5_r"]) > 0)
                mfe3 = sum(1 for e in settled_all if e[f"{PRIMARY}_mfe"] is not None and e[f"{PRIMARY}_mfe"] >= X.TAIL_R)
                r3 = sum(1 for x in SS if float(x["r5_r"]) >= X.TAIL_R)
                say(f"  win rate {wins}/{len(SS)} = {X.pct(wins, len(SS))}; reached 3R realized {r3} ({X.pct(r3, len(SS))}), MFE >= 3R {mfe3} ({X.pct(mfe3, len(SS))})")
                nums[f"orb:{pop}:win_rate"] = wins / len(SS) if SS else float("nan")
        for k in (1, 2):
            bv = W.base_verdict(S, f"orb_slip{k}:{pop}", r_field=f"r5_r_slip{k}", pnl_field=f"r5_pnl_adr_slip{k}")
            W._bv_numbers(f"orb_slip{k}:{pop}", bv, nums)
            W._bv_line(say, f"{pop} at {k * 0.1:.1f}% exit slippage", bv)
            if k == 1:
                verdicts[pop + ":slip1"] = bv
        for k, t in zip((1, 2, 5), SLIP_TICKS):
            bv = W.base_verdict(S, f"orb_tick{k}:{pop}", r_field=f"r5_r_tick{k}", pnl_field=f"r5_pnl_adr_tick{k}")
            W._bv_numbers(f"orb_tick{k}:{pop}", bv, nums)
            W._bv_line(say, f"{pop} at {t * 100:.0f}c entry AND cover slippage (R - 2k / risk)", bv)
            if k == 2:
                verdicts[pop + ":tick2"] = bv
        ended = [as_1028_row(e, PRIMARY) for e in sub if e[f"{PRIMARY}_status"] == "ended_mid_walk"]
        tw = W.verdict_three_ways(S, ended, f"orb_three:{pop}", a=verdicts[pop])
        say(f"  ended_mid_walk: {len(ended)} ({dict(Counter(e[f'{PRIMARY}_ended_class'] for e in sub if e[f'{PRIMARY}_status'] == 'ended_mid_walk'))}); "
            f"(b) at the last close -> {tw['b']['verdict']}; (c) with the 1.25x haircut -> {tw['c']['verdict']}; label: {tw['label']}")
        verdicts[pop + ":label"] = tw["label"]
        say(f"  void_bad_geometry (stop under 1% above the entry): {sum(1 for e in sub if e[f'{PRIMARY}_status'] == 'void_bad_geometry')}")
        top = sorted(settled_all, key=lambda e: -e[f"{PRIMARY}_r"])[:10]
        say("  the top 10 by R:")
        X.table(say, ["ticker", "D0", "era", "entry", "stop", "R$", "exit", "reason", "R"],
                [[e["ticker"], e["d0"], e["era"], _f(e[f"{PRIMARY}_entry"]), _f(e[f"{PRIMARY}_stop"]), _f(e[f"{PRIMARY}_risk"]), _f(e[f"{PRIMARY}_exit"]),
                  e[f"{PRIMARY}_reason"], _f(e[f"{PRIMARY}_r"])] for e in top])
        say(f"  the nine variants + the beside stop rule (pre-declared; the verdict is {PRIMARY} only):")
        grid = []
        for v in ALL_VARIANTS:
            SV = [as_1028_row(e, v) for e in sub if e[f"{v}_status"] == "settled"]
            bv = W.base_verdict(SV, f"orb_{v}:{pop}")
            W._bv_numbers(f"orb_{v}:{pop}", bv, nums)
            wins = sum(1 for x in SV if float(x["r5_r"]) > 0)
            grid.append([v, bv["n"], W._fmt(bv["mean_r"]), f"[{W._fmt(bv['lo'])}, {W._fmt(bv['hi'])}]", W._fmt(bv["mean_pnl_adr"]),
                         X.pct(wins, bv["n"]), bv["tail"]["trades"], bv["verdict"]])
        X.table(say, ["variant", "n", "mean R", "95%", "ADR P&L", "win", ">=3R", "verdict"], grid)
    say("\n## The consequence (§10): a reading about THIS version, with the 10-28 line beside; nothing live changes on any cell")
    for pop in DECIDING:
        v = verdicts[pop]["verdict"]
        flag = ""
        if v.startswith("PASS") and (verdicts[pop + ":slip1"]["lo"] <= 0 or verdicts[pop + ":tick2"]["lo"] <= 0):
            flag = " [PASS at zero cost only -> read as CAN'T TELL (fill optimism): the interval's lower end is <= 0 at 0.1% exit slippage or at the 2c entry+cover row]"
        say(f"- {pop}: {v}{flag}; {verdicts[pop + ':label']}")
    say("WALK COMPLETE")
    if write:
        cols = ["ticker", "d0", "era", "population", "company_key", "decision", "pre", "s1", "s2", "s3", "adr20"] + \
               [f"{v}_{k}" for v in ALL_VARIANTS for k in blank()]
        X.write_tsv(P.episodes_out, cols, eps)
        with open(P.episodes_out + ".numbers.json", "w") as fh:
            json.dump({k: (None if isinstance(v, float) and math.isnan(v) else v) for k, v in nums.items()}, fh, indent=1, default=str)
        say.write(P.result)
    return {"episodes": eps, "numbers": nums, "lines": say.lines, "n_request": len(req), "n_checked": checked, "n_fail": len(fails)}


# ═════════════════════════════════════════════════════════════════════════════════════════════
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--request", action="store_true")
    g.add_argument("--walk", action="store_true")
    g.add_argument("--print-pins", action="store_true")
    a = ap.parse_args(argv)
    P = Paths()
    if a.print_pins:
        print("# data + imported-module pins (REGISTERED_PINS; §7 table)")
        for k in REGISTERED_PINS:
            print(f"{k}\t{X.sha_or_absent(P.f(k))}")
        print("# code pins: ABOVE the marker (the pre-pull freeze)")
        for k, v in P.code_pins().items():
            print(f"{k}\t{v}")
        print("# post-pull pins: BELOW the marker (pasted by the main loop)")
        print(f"doc_body\t{X.doc_body_sha(P.doc) if os.path.exists(P.doc) else 'ABSENT'}")
        print(f"minute_bars\t{X.sha_or_absent(P.minute_bars)}")
        print(f"minute_bars_meta\t{X.sha_or_absent(P.minute_meta)}")
        return 0
    if a.dry_run:
        return dry_run(P)
    try:
        if a.request:
            write_request(P)
            return 0
        say = X.Say()
        walk(P, say=say)
        return 0
    except GuardStop as ex:
        msg = f"REFUSED: {ex}"
        print(msg)
        with open(P.refused, "w") as fh:
            fh.write(msg + "\n")
        return 2


if __name__ == "__main__":
    sys.exit(main())
