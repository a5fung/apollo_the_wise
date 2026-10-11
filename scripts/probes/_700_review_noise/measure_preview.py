"""#700 — character / line counts of the hand render (fold vs the 12,257-char baseline)."""
from pathlib import Path

t = (Path(__file__).resolve().parent / "preview_1011_by_hand.md").read_text(encoding="utf-8")
head = t.split("<<<HEAD>>>\n", 1)[1].split("<<<FOLD>>>", 1)[0].strip()
fold = t.split("<<<FOLD>>>\n", 1)[1].split("<<<END>>>", 1)[0].strip()
extra = t.split("<<<FIRST_RUN_EXTRA>>>\n", 1)[1].split("<<<END>>>", 1)[0].strip()
print(f"head: {len(head)} chars, {head.count(chr(10)) + 1} lines (checked line {len(head.splitlines()[-1])} chars)")
print(f"fold steady-state: {len(fold)} chars, {fold.count(chr(10)) + 1} lines  -> {100 * len(fold) / 12257:.0f}% of 12,257")
print(f"fold first-run (10-18): {len(fold) + len(extra) + 2} chars -> {100 * (len(fold) + len(extra) + 2) / 12257:.0f}% of 12,257")
