#!/usr/bin/env python3
"""#702 P4b vision step ($0): side-by-side review images for doubtful line reads - his chart as streamed (left panel) next
to OUR daily bars over the same window with the reader's line drawn in blue. Used by the main loop and, for the cases it
cannot settle, the operator (he offered a cursory look 2026-10-18).

    python vision_review_pairs.py --cases cases.json --out DIR
cases.json = [{"n": 1, "frame_id": "b1_07", "ticker": "NET", "screen": "2021-04-22", "role": "top",
               "start_date": ..., "start_price": ..., "end_date": ..., "end_price": ...}, ...]
"""
import argparse
import datetime as dt
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vision_score as vsc  # noqa: E402

QM = vsc.QM


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    cases = json.load(open(a.cases))
    import csv
    rename = {r["polygon_ticker"]: r["alpaca_symbol"] for r in csv.DictReader(open(f"{QM}/ext_2016_2022/rename_map.tsv"), delimiter="\t")}
    tick = {c["ticker"] for c in cases}
    A, P, S = vsc.load_bars(tick | {rename[t] for t in tick if t in rename})
    for c in cases:
        ser = vsc.series_asof(c["ticker"], c["screen"], A, P, S) or vsc.series_asof(rename.get(c["ticker"], ""), c["screen"], A, P, S)
        dates, hi, lo, cl = ser
        od = np.array([dt.date.fromisoformat(x).toordinal() for x in dates])
        d1, d2 = vsc.ordinal(c["start_date"]), vsc.ordinal(c["end_date"])
        lo_d, hi_d = min(d1, d2) - 120, min(max(d1, d2) + 60, dt.date.fromisoformat(c["screen"]).toordinal())
        m = (od >= lo_d) & (od <= hi_d)
        fig, ax = plt.subplots(figsize=(10, 7.5), dpi=100)
        fig.patch.set_facecolor("black"); ax.set_facecolor("black")
        x = od[m]
        up = cl[m] >= np.r_[cl[m][0], cl[m][:-1]]
        ax.vlines(x, lo[m], hi[m], color=np.where(up, "#22c55e", "#ef4444"), linewidth=1.2)
        ax.plot([d1, d2], [c["start_price"], c["end_price"]], color="#38bdf8", linewidth=2.5,
                label=f"reader's {c['role']} line")
        ax.legend(loc="upper left", facecolor="black", labelcolor="white")
        ticks = [o for o in range(int(x.min()), int(x.max()) + 1) if dt.date.fromordinal(o).day == 1]
        ax.set_xticks(ticks, [dt.date.fromordinal(o).strftime("%b %y") for o in ticks], color="white", fontsize=8)
        ax.tick_params(axis="y", colors="white"); ax.yaxis.tick_right()
        ax.set_title(f"#{c['n']}  {c['ticker']}  our daily bars, as shown on {c['screen']}", color="white")
        p = os.path.join(a.out, f"_bars_{c['n']}.png"); fig.savefig(p, facecolor="black", bbox_inches="tight"); plt.close(fig)
        frame = Image.open(c.get("frame_path") or f"{QM}/vision/frames/{c['frame_id']}.png").convert("RGB")
        left = frame.crop((0, 55, 1000, 1000)) if c.get("daily_panel", "left") == "left" else frame.resize((1280, 720))
        bars = Image.open(p).convert("RGB")
        h = max(left.height, bars.height)
        out = Image.new("RGB", (left.width + bars.width + 20, h + 40), (255, 255, 255))
        out.paste(left, (0, 40)); out.paste(bars, (left.width + 20, 40))
        from PIL import ImageDraw
        ImageDraw.Draw(out).text((10, 10), f"#{c['n']}  {c['ticker']} {c['screen']}  LEFT: his chart on stream   RIGHT: our bars + the reader's {c['role']} line (blue)  "
                                           f"{c['start_date']} {c['start_price']} -> {c['end_date']} {c['end_price']}", fill=(0, 0, 0))
        out.save(os.path.join(a.out, f"case_{c['n']}.png"))
        os.remove(p)
        print("case", c["n"], c["ticker"], "ok")


if __name__ == "__main__":
    sys.exit(main())
