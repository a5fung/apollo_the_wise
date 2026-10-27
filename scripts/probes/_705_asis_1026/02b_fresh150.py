#!/usr/bin/env python3
"""#705 as-is step 6a — the plan's one re-test after the first agreement fell below its bar (§4.1 step 5: "the sheet's wording is
fixed, and BOTH readers re-read a fresh 150 (a disclosed event, once; a second failure stops step 6a and goes to him)"). Draws 150
statements NEITHER reader has seen in an agreement sample: 100 from the price batch (`reader1_t1_price.tsv`) and 50 from the other
strata (`reader1_rest_b*.tsv`), both excluding the first `reader2_150.tsv` rows, through `rng_for` with named keys (seed 705), in a
seeded shuffled order with new ids F001..F150. Writes ONE blank sheet both fresh readers read: `sheets/reread_150.tsv`. Reads only
this read's sheets; no rule module, no bar, no window."""
import csv, glob, importlib, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..", "..")))
C = importlib.import_module("scripts.probes._705_asis_1026.asis_common")
SH = os.path.join(C.OUT_DIR, "sheets")
LABELS = ["ticker_ident", "ticker", "ticker_inferred", "his_trade", "action", "side", "date_pinnable", "price_stated", "price_value",
          "price_garbled", "price_kind", "shares", "dollar_result", "note"]

def read(path):
    with open(C.checked(path), encoding="utf-8") as fh:
        r = csv.DictReader(fh, delimiter="\t")
        return r.fieldnames, list(r)

def draw(pool, n, key):
    pool = sorted(pool, key=lambda s: s["stmt_id"])
    idx = sorted(C.rng_for(key).choice(len(pool), size=n, replace=False).tolist())
    return [pool[i] for i in idx]

def main() -> int:
    out = os.path.join(SH, "reread_150.tsv")
    if os.path.exists(out):
        raise SystemExit(f"{out} exists; refusing to redraw (the re-test is drawn once)")
    cols, t1 = read(os.path.join(SH, "reader1_t1_price.tsv"))
    rest = []
    for p in sorted(glob.glob(os.path.join(SH, "reader1_rest_b*.tsv"))):
        rest += read(p)[1]
    _, first = read(os.path.join(SH, "reader2_150.tsv"))
    seen = {r["stmt_id"] for r in first}
    t1p = [r for r in t1 if r["stmt_id"] not in seen]
    restp = [r for r in rest if r["stmt_id"] not in seen]
    pick = draw(t1p, 100, "asis_6a_reread_price") + draw(restp, 50, "asis_6a_reread_rest")
    perm = C.rng_for("asis_6a_reread_order").permutation(len(pick)).tolist()
    rows = []
    for k, i in enumerate(perm):
        r = dict(pick[i]); r["sid"] = f"F{k + 1:03d}"
        r.update({c: "" for c in LABELS})
        rows.append(r)
    assert len({r["stmt_id"] for r in rows}) == 150 and not ({r["stmt_id"] for r in rows} & seen)
    with open(out, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, delimiter="\t", lineterminator="\n")
        w.writeheader(); w.writerows(rows)
    print(f"fresh 150: pools price {len(t1p)} / rest {len(restp)} (first sample's {len(seen)} excluded); wrote {out} ({C.sha(out)[:16]})")
    return 0

if __name__ == "__main__":
    sys.exit(main())
