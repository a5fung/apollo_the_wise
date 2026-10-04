"""#655 verify — A cumulative over 19 nights (no look-ahead), K sensitivity, and B's regrowth cost."""
import sys, collections
sys.argv = ["x"]
exec(open("/private/tmp/claude-501/-Users-alvinfung-apollo-the-wise/d30e3944-e07e-4b44-97de-010acba78d0b/scratchpad/655_study/verify_b.py").read().split("nights = [D for D")[0])
nights = [D for D in dates if D >= date(2026, 9, 8)]
fails, boards = {}, {}
for D in nights:
    b = board(D); boards[D] = b
    ex, _ = masked(D); us = tc.usable_set(ex)
    fails[D] = set(tc.compute_g3(b, ex, us, scores, sector)["fail_list"])
last = nights[-1]
for K in (2, 3, 4, 5):
    streak = collections.defaultdict(int); retired = {}
    g3p = g4p = g3p_ab = g4p_ab = 0
    for D in nights:
        names = {t["name"] for t in boards[D]}
        for n in names: streak[n] = streak[n] + 1 if n in fails[D] else 0
        for n in names:
            if streak[n] >= K and n not in retired: retired[n] = D
        live = [t for t in boards[D] if t["name"] not in retired]
        nf = sum(1 for t in live if t["name"] in fails[D]); g3 = 100 * (len(live) - nf) / len(live)
        sm = sum(1 for t in live if len(t["tickers"]) < 3)
        g3p += g3 >= 90; g4p += 100 * sm / len(live) <= 10
        lab = [t for t in live if not (t["stage"] == "Fading" and len(t["tickers"]) < 3)]
        nf2 = sum(1 for t in lab if t["name"] in fails[D]); sm2 = sum(1 for t in lab if len(t["tickers"]) < 3)
        g3p_ab += 100 * (len(lab) - nf2) / len(lab) >= 90; g4p_ab += 100 * sm2 / len(lab) <= 10
    bl = {t["name"] for t in boards[last]}
    fk = [n[:40] for n in retired if n in bl and n not in fails[last]]
    print(f"K={K}: retire events {len(retired)} | false kills (on 10-02 board AND pass 10-02) {len(fk)} {fk}")
    print(f"      nights passing (drift-free): A alone G3 {g3p}/19 G4 {g4p}/19 | A+B G3 {g3p_ab}/19 G4 {g4p_ab}/19")
# Size of retire events by stage/age at retirement under K=3 (north-star: how many were Nascent / young?)
# B regrowth cost over the full 60-day history
shell_nights = 0; regrew = []
for n, rows in by_name.items():
    for i, r in enumerate(rows):
        if r["stage"] == "Fading" and 0 < len(r["tickers"]) < 3:
            shell_nights += 1
    # a shell episode = first shell night after a non-shell night; regrowth = later row >=3 members, non-Fading
    i = 0
    while i < len(rows):
        r = rows[i]
        if r["stage"] == "Fading" and 0 < len(r["tickers"]) < 3:
            j = i
            while j < len(rows) and rows[j]["stage"] == "Fading" and 0 < len(rows[j]["tickers"]) < 3: j += 1
            if j < len(rows) and rows[j]["stage"] != "Retired" and len(rows[j]["tickers"]) >= 3:
                later_ok = sum(1 for x in rows[j:] if x["stage"] not in ("Fading", "Retired") and len(x["tickers"]) >= 3)
                regrew.append((n[:40], r["theme_date"], j - i, later_ok, max(len(x["tickers"]) for x in rows[j:])))
            i = j
        else: i += 1
print("B: shell-nights (Fading, 1-2 members) in 60d:", shell_nights, "| episodes that regrew to >=3 next:", len(regrew),
      "| of which >=5 later non-Fading >=3-member nights:", sum(1 for x in regrew if x[3] >= 5))
for x in sorted(regrew, key=lambda x: -x[3])[:14]: print("   ", x)
