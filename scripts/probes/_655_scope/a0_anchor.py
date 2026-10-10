"""#655 scope — anchor: rebuild each of the 10 nights' G3 from the capture and compare to the stored row."""
from board import NIGHTS, STORED, ordered_board, g3
for d in NIGHTS:
    th, missing, extra = ordered_board(d)
    st = {t["name"]: t for t in STORED[d]["g3"]["themes"]}
    sizes_ok = sum(len(t["tickers"]) == st[t["name"]]["size"] for t in th)
    r = g3(th, d)
    same = sum(x["pass_g3"] == st[x["name"]]["pass_g3"] for x in r["themes"])
    print(f"{d} board {len(th)} (missing {len(missing)}, extra {len(extra)}) sizes match {sizes_ok}/{len(th)} | "
          f"G3 rebuild {r['pass']}/{r['n_judgeable']} vs stored {STORED[d]['g3']['pass']}/{STORED[d]['g3']['n_judgeable']} | "
          f"verdicts identical {same}/{len(r['themes'])}")
