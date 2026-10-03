"""#687 B — build the golden file that pins the LIVE depth stop to the ANALYSIS walker.

The live function is `agents/market_intelligence/broker/exit_logic.depth_stop_price`; the walker
is `walk()` in `scripts/probes/_687/mechanics.py` (the D10 arm's resting stop). This script does
NOT copy the walker's arithmetic and does NOT import `mechanics.py` (importing it truncates its
own tracked output file `mechanics_out.txt` at module load). It reads the walker's resting-stop
lines out of `mechanics.py` as TEXT — the block from `floor = max(hard, entry) …` to
`rest = round(floor, 2)` — and executes exactly those lines on each case, so the golden values
are the walker's own, and a later edit to those lines changes the recorded `walker_block_sha256`.

Cases: hand-picked edges (no line yet, line below the floor, breakeven armed with a many-decimal
entry, no ADR, a huge ADR, half-cent rounding boundaries — including at least one where
`line_r - 1.0*adr*line_r` and `line_r*(1-adr)` round to DIFFERENT cents, so the parity pin has
teeth) plus seeded random cases over realistic price / ADR ranges.

$0, offline, deterministic (seed 687). Writes `tests/fixtures/687_depth_stop_golden.json`.
Run: python scripts/probes/_687/depth_stop_golden.py
"""
from __future__ import annotations

import hashlib
import json
import random
import textwrap
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
WALKER = REPO / "scripts" / "probes" / "_687" / "mechanics.py"
OUT = REPO / "tests" / "fixtures" / "687_depth_stop_golden.json"

_START = "floor = max(hard, entry) if be_active else hard"
_END = "rest = round(floor, 2)"


def walker_block() -> str:
    """The walker's resting-stop lines, verbatim (the FIRST occurrence — `walk()`)."""
    lines = WALKER.read_text().splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.strip() == _START)
    end = next(i for i in range(start, len(lines)) if lines[i].strip() == _END)
    return textwrap.dedent("\n".join(lines[start:end + 1]))


def walker_rest_fn(block: str):
    """Wrap the walker's lines into a function of the inputs they read. `line_rests=False`,
    `adr_stop=True` is the D10 arm (the depth rule)."""
    src = ("def _rest(hard, entry, be_active, line, adr_pct, line_rests=False, adr_stop=True):\n"
           + textwrap.indent(block, "    ") + "\n    return rest\n")
    ns: dict = {}
    exec(compile(src, str(WALKER) + ":walk()[resting-stop block]", "exec"), ns)  # noqa: S102
    return ns["_rest"]


def _cases() -> list[dict]:
    hand = [
        # (label, hard, entry, be_active, line, adr_pct)
        ("no line yet: the floor", 58.08, 63.15, False, None, 0.05),
        ("line below the hard stop: the floor", 58.08, 63.15, False, 57.10, 0.05),
        ("line exactly at the floor: not trail-governed", 58.08, 63.15, False, 58.08, 0.05),
        ("depth under the floor: the floor wins", 58.08, 63.15, False, 60.00, 0.08),
        ("trail-governed, depth above the floor", 58.08, 63.15, False, 70.12, 0.05),
        ("breakeven armed, many-decimal entry", 27.09, 30.211219, True, 33.47, 0.06),
        ("breakeven armed, depth below entry: entry wins", 27.09, 30.211219, True, 31.00, 0.06),
        ("no ADR20 (fewer than 10 sessions): the floor", 58.08, 63.15, False, 70.12, None),
        ("ADR20 of zero: the floor", 58.08, 63.15, False, 70.12, 0.0),
        ("huge ADR20: the floor", 9.75, 10.55, False, 14.00, 0.60),
        ("VICR-like: line 239.38", 201.13, 211.50, True, 239.38, 0.041),
        ("KOD-like: line 70.40, be armed", 58.08, 63.15, True, 70.40, 0.072),
        ("line with 3+ decimals rounds first", 10.00, 10.50, False, 12.3456, 0.031),
        ("sub-$10 name", 4.10, 4.55, False, 5.237, 0.09),
    ]
    out = [dict(label=l, hard=h, entry=e, be_active=b, line=ln, adr_pct=a)
           for l, h, e, b, ln, a in hand]

    # Half-cent boundaries where the two algebraic forms round differently: search a grid
    # deterministically and keep the first few found.
    found = 0
    for cents in range(1000, 40000, 7):
        line_r = cents / 100
        for adr_bp in range(150, 1200, 13):
            adr = adr_bp / 10000
            a = round(line_r - 1.0 * adr * line_r, 2)
            b = round(line_r * (1 - adr), 2)
            if a != b:
                out.append(dict(label=f"half-cent boundary: forms differ ({a} vs {b})",
                                hard=round(line_r * 0.5, 2), entry=round(line_r * 0.6, 2),
                                be_active=False, line=line_r, adr_pct=adr))
                found += 1
                break
        if found >= 4:
            break

    rng = random.Random(687)
    for i in range(400):
        entry = round(rng.uniform(5.0, 400.0), rng.choice([2, 2, 4, 6]))
        orb_r = entry * rng.uniform(0.005, 0.05)
        hard = round(entry - 2 * orb_r, 2)
        be = rng.random() < 0.5
        line = None if rng.random() < 0.05 else round(entry * rng.uniform(0.85, 1.6),
                                                      rng.choice([2, 3, 4]))
        adr = None if rng.random() < 0.05 else round(rng.uniform(0.01, 0.15), 6)
        out.append(dict(label=f"random #{i}", hard=hard, entry=entry, be_active=be,
                        line=line, adr_pct=adr))
    return out


def main() -> None:
    block = walker_block()
    rest_fn = walker_rest_fn(block)
    cases = []
    for c in _cases():
        # The walker's `line` starts at the floor and is RAISED by the trail; "no line yet" is
        # the walker's own starting value (the floor) — the same thing the live function does
        # with line=None.
        line_in = c["line"] if c["line"] is not None else c["hard"]
        rest = rest_fn(c["hard"], c["entry"], c["be_active"], line_in, c["adr_pct"])
        cases.append({**c, "walker_rest": rest})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "source": "scripts/probes/_687/mechanics.py walk() — D10 resting-stop block, executed verbatim",
        "walker_block": block,
        "walker_block_sha256": hashlib.sha256(block.encode()).hexdigest(),
        "generator": "scripts/probes/_687/depth_stop_golden.py (seed 687)",
        "cases": cases,
    }, indent=1) + "\n")
    print(f"wrote {len(cases)} cases to {OUT.relative_to(REPO)}")


if __name__ == "__main__":
    main()
