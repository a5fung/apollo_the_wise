#!/usr/bin/env python3
"""Shared loader for the 9M-share-count vs relative-volume read (2026-10-16).

Reads #684's captured files ONLY (scripts/probes/_684/: features.tsv, daily.tsv.gz, orb.tsv, pop.tsv).
No prod contact, no write outside this directory. Nothing here reads a bar AFTER the gap day:
`gap_day_bar` returns the scan-date bar itself and `_guard` asserts it. Outcomes are attached only by
read.py (via #684's own study.add_outcomes), never here.

Added columns (all known at the gap-day CLOSE unless tagged otherwise):
  SC_shares          gap-day total shares (mi_daily_closes.volume on scan_date; Polygon grouped daily,
                     consolidated, split-ADJUSTED like every bar in that table)
  SC_ge9m            1 if SC_shares >= 9,000,000 else 0  (Bonde's "EP 9M" rule)
  SC_log_shares      log10(SC_shares)  (continuous form, used for terciles/AUC — monotone, same ranks)
  SC_dollar_gapday   SC_shares x gap-day close
  E_orb_shares       shares 09:30-09:44 ET (sum of 15 one-minute bars; orb.tsv orb_vol, mi_intraday_bars),
                     only when all >=12 of the 15 bars exist (#684's O945_covered rule) — tagged 0945
  E_orb_share_of_day E_orb_shares / SC_shares (feed check: consolidated minute bars give ~0.1-0.4 on a gap day)
"""
from __future__ import annotations

import gzip
import math
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE.parent / "_684"
sys.path.insert(0, str(SRC))

NINE_M = 9_000_000


def load_daily_raw() -> dict[str, list[tuple[str, float, float, float, float, float]]]:
    out: dict[str, list] = defaultdict(list)
    with gzip.open(SRC / "daily.tsv.gz", "rt") as fh:
        header = None
        for line in fh:
            line = line.rstrip("\n")
            if not line or line.startswith("("):
                continue
            parts = line.split("|")
            if header is None:
                header = parts
                continue
            t, d, o, h, l, c, v = parts
            if not (o and h and l and c):
                continue
            out[t].append((d, float(o), float(h), float(l), float(c), float(v) if v else None))
    for t in out:
        out[t].sort()
    return out


def load_psv(path: Path) -> list[dict]:
    rows = []
    with path.open() as fh:
        header = None
        for line in fh:
            line = line.rstrip("\n")
            if not line or line.startswith("(") or line.startswith("Output format") or line.startswith("Field separator"):
                continue
            parts = line.split("|")
            if header is None:
                header = parts
                continue
            if len(parts) != len(header):
                continue
            rows.append(dict(zip(header, parts)))
    return rows


def gap_day_bar(bars: list, d: str):
    for b in bars:
        if b[0] == d:
            _guard(b, d)
            return b
    return None


def _guard(b, d: str) -> None:
    assert b[0] == d, "only the gap-day bar may be read here"


def load_rows() -> list[dict]:
    import study  # #684's own loader (features.tsv) — imported, not copied
    rows = study.load_features()
    daily = load_daily_raw()
    orb = {(r["ticker"], r["scan_date"]): r for r in load_psv(SRC / "orb.tsv")}
    for r in rows:
        b = gap_day_bar(daily.get(r["ticker"], []), r["scan_date"])
        v = b[5] if b else None
        r["SC_shares"] = v if (v is not None and v > 0) else None
        r["SC_ge9m"] = (1.0 if v >= NINE_M else 0.0) if r["SC_shares"] is not None else None
        r["SC_log_shares"] = math.log10(v) if r["SC_shares"] is not None else None
        r["SC_dollar_gapday"] = (v * b[4]) if r["SC_shares"] is not None else None
        ob = orb.get((r["ticker"], r["scan_date"]))
        e = None
        if ob and r.get("O945_covered") == 1.0 and ob.get("orb_vol"):
            e = float(ob["orb_vol"])
        r["E_orb_shares"] = e
        r["E_log_orb_shares"] = math.log10(e) if (e is not None and e > 0) else None
        r["E_orb_share_of_day"] = (e / r["SC_shares"]) if (e is not None and r["SC_shares"]) else None
    return rows
