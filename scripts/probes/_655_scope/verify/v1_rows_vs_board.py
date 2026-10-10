"""verify #655: is 'no non-Retired row dated d' the same as 'off the get_active_themes(7) board on d'? $0."""
import sys; from pathlib import Path; sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from collections import defaultdict
from load import load
from board import board_at
B = load()
on = defaultdict(set)
for r in B["themes"]:
    if r["stage"] != "Retired" and r["tickers"]:
        on[r["d"]].add(r["name"])
nights = sorted(on)
for d in nights[-15:]:
    bd = {r["name"] for r in board_at(d) if r["tickers"]}
    print(d, "rows", len(on[d]), "board", len(bd), "board-not-row", len(bd - on[d]), "row-not-board", len(on[d] - bd), sorted(bd - on[d])[:3])
