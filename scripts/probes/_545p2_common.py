"""#545 Phase 2 -- shared loaders. Parses the psql ASCII-table captures this card pulled
(read-only, 2026-09-22) and merges them with the existing scripts/ep_replay_data/ captures,
WITHOUT overwriting any of them. Every function here is read-only against local files.
"""
from __future__ import annotations

import gzip
import re
import sys
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

_ET = ZoneInfo("America/New_York")

SEP_RE = re.compile(r"^-+(\+-+)*$")


def parse_psql_section(text: str, section: str) -> list[dict]:
    """Extract one `=== SECTION ===` block from a captured psql -c/-f run and return its
    rows as dicts, keyed by the printed column headers. Stops at the blank line psql emits
    before the "(N rows)" footer. Returns [] if the section has 0 rows."""
    lines = text.splitlines()
    start = None
    for i, ln in enumerate(lines):
        if ln.strip() == f"=== {section} ===":
            start = i + 1
            break
    if start is None:
        raise ValueError(f"section {section!r} not found")
    block = []
    for ln in lines[start:]:
        if ln.strip() == "" or ln.strip().startswith("==="):
            break
        block.append(ln)
    if len(block) < 2:
        return []
    header = [h.strip() for h in block[0].split("|")]
    # block[1] is the ---+--- separator
    rows = []
    for ln in block[2:]:
        if SEP_RE.match(ln.strip()) or ln.strip().startswith("("):
            continue
        cells = [c.strip() for c in ln.split("|")]
        if len(cells) != len(header):
            continue
        rows.append(dict(zip(header, cells)))
    return rows


def load_daily_extra(paths: list[Path], section: str,
                      daily: dict[str, dict[date, dict]]) -> int:
    """Merge one psql DAILY-shaped section (ticker|trade_date|open_price|high_price|
    low_price|close|volume) into an existing `daily` dict (ep_replay.load_daily()'s shape).
    In-place; returns rows merged."""
    n = 0
    for path in paths:
        text = path.read_text()
        for r in parse_psql_section(text, section):
            t, d = r["ticker"], date.fromisoformat(r["trade_date"])
            daily.setdefault(t, {})[d] = {
                "o": float(r["open_price"]) if r["open_price"] else None,
                "h": float(r["high_price"]) if r["high_price"] else None,
                "l": float(r["low_price"]) if r["low_price"] else None,
                "c": float(r["close"]) if r["close"] else None,
                "v": float(r["volume"]) if r["volume"] else None,
            }
            n += 1
    return n


def load_minutes_extra_psql(path: Path, section: str,
                            minutes: dict) -> int:
    """Merge one psql MIN-shaped section (ticker|et_min|open|high|low|close|volume —
    et_min 'YYYY-MM-DD HH24:MI') into an existing `minutes` dict (ep_replay.load_minutes()'s
    shape). In-place; returns rows merged."""
    n = 0
    text = path.read_text()
    for r in parse_psql_section(text, section):
        dt = datetime.strptime(r["et_min"], "%Y-%m-%d %H:%M").replace(tzinfo=_ET)
        minutes.setdefault((r["ticker"], dt.date()), []).append(
            {"m": dt, "o": float(r["open"]), "h": float(r["high"]),
             "l": float(r["low"]), "c": float(r["close"])})
        n += 1
    return n


def load_minutes_extra_gz(path: Path, minutes: dict) -> int:
    """Merge one Alpaca-fetch-shaped gz (=== MIN === section, ticker|et_min|o|h|l|c|v,
    et_min 'YYYY-MM-DD HH:MM') into an existing `minutes` dict. Same format
    _623_fetch_bars.py / _545p2_fetch_bars.py write. In-place; returns rows merged."""
    n = 0
    with gzip.open(path, "rt") as fh:
        section = None
        for line in fh:
            line = line.rstrip("\n")
            if line.startswith("==="):
                section = line
                continue
            if section != "=== MIN ===" or line.startswith("ticker|") or line.startswith("#FAILED"):
                continue
            p = line.split("|")
            if len(p) != 7:
                continue
            dt = datetime.strptime(p[1], "%Y-%m-%d %H:%M").replace(tzinfo=_ET)
            minutes.setdefault((p[0], dt.date()), []).append(
                {"m": dt, "o": float(p[2]), "h": float(p[3]),
                 "l": float(p[4]), "c": float(p[5])})
            n += 1
    return n


def sort_minutes(minutes: dict) -> None:
    for bars in minutes.values():
        bars.sort(key=lambda b: b["m"])


# ── ATR fidelity check: parse the ORIGINAL 1.5xATR gate text mi_live_trades logged ──────

ATR_RE = re.compile(r"ORB range \$?([\d.]+).*?1\.5x ATR \$?([\d.]+)")


def parse_live_gate_text(skip_reason: str) -> tuple[float, float] | None:
    """Extract (orb_range$, X$) from the SETUP_STOP_TOO_WIDE text
    ('ORB range $X.XX (Y.Y%) > 1.5x ATR $Z.ZZ'). Returns None if the row uses a different
    gate's wording (TLRY 2026-04-23: 'stop distance NN.N% > 15%' -- a DIFFERENT check,
    order_manager.prepare_prior_day_low_orb_order's own 15%-of-orb_high cap, not the
    1.5xATR gate validate_orb_entry applies -- tagged, not silently coerced).

    ⚠ The second value is whatever the LIVE code printed under the label "1.5x ATR $Z" at
    WRITE time -- it is NOT reliably raw ATR14. `validate_orb_entry`'s CURRENT format string
    prints atr_14 itself (`filters.py:221`), but for 8 of 10 still-refused 2026-09-22 rows
    this value equals 1.5 x the harness's own atr14_abs() to within 2% -- i.e. it was the
    1.5xATR THRESHOLD, not the ATR, at those write times (a label that outlived a format
    change, or an earlier code path that computed it that way; not chased further). Compare
    it to `1.5 * atr14_abs(...)`, not to `atr14_abs(...)` directly, or every comparable row
    will read as a false ~33% divergence (docs/analysis/545_phase2_population_gap_2026-09-22.md
    § Method — the mistake this comment exists to prevent repeating)."""
    m = ATR_RE.search(skip_reason)
    if not m:
        return None
    return float(m.group(1)), float(m.group(2))
