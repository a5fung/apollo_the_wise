#!/usr/bin/env python3
"""#717: the two outcome-blind sheets of the rating — 12 High, 12 Low / Not (each 4 dated + 8 widened, seed 1111).
Charts end on `hi` (the fixtures hold nothing later); the buy point is dashed from the range's start; the window is shaded.

    python3 scripts/probes/_717_qm_confidence_1111/02_sheets.py"""
import random
import sys

sys.path.insert(0, "scripts/probes/_717_qm_confidence_1111")
import rating as R  # noqa: E402
import sheet as S  # noqa: E402

HERE = "scripts/probes/_717_qm_confidence_1111/"
res = [(b, R.rate(b)) for b in R.load()]
rng = random.Random(1111)
for name, tiers in (("high", ("High",)), ("low", ("Low", "Not"))):
    items = []
    for s, k in (("dated", 4), ("widened", 8)):
        pool = [x for x in res if x[0]["set"] == s and x[1]["tier"] in tiers]
        items += rng.sample(pool, k)
    rng.shuffle(items)
    S.render(items, HERE + f"sheet_{name}.png",
             f"Qullamaggie buys rated {' / '.join(tiers)} — ~1 year of daily bars ending on the last day of the buy window (shaded); "
             "dashed = the rated buy point, drawn from the start of its range. EMA10 blue, EMA21 red, SMA50 green, SMA200 purple.",
             f"#717 confidence sheet '{name}': 4 dated + 8 widened drawn at random (seed 1111), shuffled.\n"
             "letter|set|ticker|lo|hi|tier|reason|buy_point|day_cleared|range_len|his_label",
             lambda b, r: "|".join(str(x) for x in (b["set"], b["ticker"], b["lo"], b["hi"], r["tier"], r["reason"],
                                                    "" if r["level"] is None else round(r["level"], 2),
                                                    "" if r["level"] is None else b["dates"][r["t"]], r["len"] or "", b["row"].get("his_label", ""))),
             bars_shown=160)
    print(open(HERE + f"sheet_{name}.png.key_do_not_show.txt").read())
