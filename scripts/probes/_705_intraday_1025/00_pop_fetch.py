"""#705 intraday layer — 00: outcome-free population + fetch-list derivation for the registration of 2026-10-25
(docs/analysis/cb_intraday_layer_prereg_2026-10-25.md).
Reads: entries.tsv / snapshots.tsv (names, dates, clocks), the calendar pickle (dates), the type tables, event DATES, the minute
fetch logs (_done.psv) and minute-tree date-file listings. Opens NO price bar. Imports 01_rev.py read-only for its loaders."""
import sys, os, importlib.util, collections, hashlib
import numpy as np

REV = "/Users/alvinfung/apollo_the_wise/scripts/probes/_705_reverse_1024/01_rev.py"
spec = importlib.util.spec_from_file_location("rev01", REV)
rev = importlib.util.module_from_spec(spec); sys.modules["rev01"] = rev; spec.loader.exec_module(rev)

OUT = sys.argv[1] if len(sys.argv) > 1 else "/tmp/intraday_pop_out"
os.makedirs(OUT, exist_ok=True)
lines = []
def say(s=""):
    print(s); lines.append(s)

C = rev.load_core(say)
S, buys, cal, CI, sn = C["S"], C["buys"], C["cal"], C["CI"], C["sn"]
done, files = rev.load_done_all()
trees = tuple(t for t in ("A", "B", "EP", "EP2", "REV") if t in done)
say(f"- minute trees with fetch logs: {trees}; date files per tree: " + ", ".join(f"{t} {len(files[t])}" for t in trees))

# ---- streams per year (snapshot frames), for the sparsity context ----------------------------------------------------------
yr = sn["date"].str[:4]
say("- stream frames per year (snapshots / distinct videos / distinct session dates): " +
    "; ".join(f"{y}: {int((yr == y).sum())} / {sn.loc[yr == y, 'vid'].nunique()} / {sn.loc[yr == y, 'date'].nunique()}" for y in sorted(yr.unique())))

def cov(b):
    tk = rev.bar_sym(b.E, b.sym_a, b.sym)
    return rev.minute_state(b.E, tk, done, files, trees)

def width_stats(bs):
    w = [rev.bracket_width(b) for b in bs if b.in_bracket]
    w = [x for x in w if x is not None]
    if not w:
        return "n/a"
    return f"median {np.median(w):.1f} min (q25 {np.percentile(w, 25):.0f}, q75 {np.percentile(w, 75):.0f})"

def describe(label, bs):
    inb = [b for b in bs if b.in_bracket]
    pre = [b for b in bs if b.pre_flat_bracket]
    first_in = [b for b in bs if b.first_clock]
    cv = collections.Counter(cov(b).split("/")[0] for b in bs)
    cvb = collections.Counter(cov(b).split("/")[0] for b in inb)
    hx = [b for b in bs if b.has_exit]
    held = [b.trade_days() for b in hx]
    hb = [b for b in bs if b.held_before_0935]
    say(f"  {label}: n {len(bs)} | first seen in session {len(first_in)} | in-session brackets {len(inb)} ({width_stats(bs)}; minutes on E: {dict(cvb)}) | "
        f"pre-market-flat brackets {len(pre)} | held before 09:35 {len(hb)} | exits known {len(hx)} (held to exit_hi median {np.median(held) if held else float('nan'):.0f} sessions; "
        f"exit window 1 session: {sum(1 for b in hx if b.exit_window_len() == 1)}) | minutes on E: {dict(cv)}")
    return inb

dec_used = S["dec_used"]
ex_nf, ex_all = S["ex_nf"], S["ex_all"]
nc_ex = [b for b in S["nc"] if b.wl == 1 and not b.flicker and b.type_ok and not b.inverted and not b.same_day_rebuy]

def half(E):
    return "H1" if E[5:7] <= "06" else "H2"

say("\n## POPULATIONS PER YEAR (after the §2b gate: type / inverted / same-day re-buy), dated deciding and exact-day no-event buys")
for Y in (2017, 2018, 2019, 2020, 2021, 2022, 2023):
    say(f"- {Y}")
    dated = [b for b in dec_used if b.year == Y]
    und_nf = rev.gate_steps([b for b in ex_nf if b.year == Y])[0]
    und_all = rev.gate_steps([b for b in ex_all if b.year == Y])[0]
    und_fl = [b for b in und_all if b.flicker]
    describe("dated deciding", dated)
    describe("undated exact-day non-flicker", und_nf)
    describe("undated exact-day flickers", und_fl)
    if Y == 2022:
        for h in ("H1", "H2"):
            say(f"  -- 2022 {h}:")
            describe("dated deciding", [b for b in dated if half(b.E) == h])
            describe("undated exact-day non-flicker", [b for b in und_nf if half(b.E) == h])
            describe("undated exact-day flickers", [b for b in und_fl if half(b.E) == h])
        # the previous check window ended 2022-06-14
        say(f"  -- 2022 after 2022-06-14 (outside the previous check window): dated {sum(1 for b in dated if b.E > '2022-06-14')}, "
            f"undated nf {sum(1 for b in und_nf if b.E > '2022-06-14')}, flickers {sum(1 for b in und_fl if b.E > '2022-06-14')}")
    say(f"  never-a-candidate stocks, exact-day non-flicker: {sum(1 for b in nc_ex if b.year == Y)}")

# ---- the proposed sets --------------------------------------------------------------------------------------------------------
FIT = rev.FIT_WIN                      # the registered fit window 2020-01-27..12-31 (sets equal the previous registration's)
CHK_YEARS = (2019, 2023)
BESIDE = rev.CHECK_WIN                 # the previous read's check window: read for L1-L6, S1-S8, the daily exit list
def inwin(bs, w): return [b for b in bs if w[0] <= b.E <= w[1]]
sets = {}
sets["fit_dated"] = inwin(dec_used, FIT)
sets["fit_und"] = rev.gate_steps(inwin(ex_all, FIT))[0]
sets["chk_dated"] = [b for b in dec_used if b.year in CHK_YEARS]
sets["chk_und"] = rev.gate_steps([b for b in ex_all if b.year in CHK_YEARS])[0]
sets["chk_dated_2022H2"] = [b for b in dec_used if b.E > rev.CHECK_WIN[1] and b.year == 2022]
sets["chk_und_2022H2"] = rev.gate_steps([b for b in ex_all if b.E > rev.CHECK_WIN[1] and b.year == 2022])[0]
sets["beside_dated"] = inwin(dec_used, BESIDE)
sets["beside_und"] = rev.gate_steps(inwin(ex_all, BESIDE))[0]
sets["listed_2017"] = [b for b in dec_used if b.year <= 2018] + rev.gate_steps([b for b in ex_all if b.year <= 2018])[0]
sets["listed_2020_pre0127"] = [b for b in dec_used if "2020-01-01" <= b.E < FIT[0]] + rev.gate_steps([b for b in ex_all if "2020-01-01" <= b.E < FIT[0]])[0]
sets["virgin_all"] = sets["chk_dated"] + sets["chk_und"] + sets["chk_dated_2022H2"] + sets["chk_und_2022H2"] + sets["listed_2020_pre0127"]
say("\n## THE PROPOSED SETS")
for k, v in sets.items():
    nf = [b for b in v if not b.flicker]
    say(f"- {k}: {len(v)} (non-flicker {len(nf)}; in-session brackets {sum(1 for b in v if b.in_bracket)} [non-flicker {sum(1 for b in nf if b.in_bracket)}]; "
        f"exits known {sum(1 for b in v if b.has_exit)}; era B {sum(1 for b in v if b.E >= '2022-04-01')})")

# ---- the fetch list: minute bars for the hold (and the 60-minute 20-EMA warm-up) ------------------------------------------------
WARM = 10        # sessions before the buy day (70 clock-anchored 60-minute bars for a 20-bar EMA)
TAIL = 20        # sessions after exit_hi the chosen rule may still run before the walk is cut
NOEXIT = 20      # a still-held trade (no exit window): the buy day + 20
def hold_pairs(bs, warm, tail, noexit):
    need = collections.Counter(); pairs = {}
    for b in bs:
        if b.Ei < 0:
            need["no_calendar_index"] += 1; continue
        i0 = max(0, b.Ei - warm)
        if b.has_exit:
            j1 = min(b.exit_hi_i + tail, len(cal) - 1)
        else:
            j1 = min(b.Ei + noexit, len(cal) - 1)
        for i in range(i0, j1 + 1):
            d = cal[i]
            tk = rev.bar_sym(d, b.sym_a, b.sym)
            kind = "warmup" if i < b.Ei else ("buyday" if i == b.Ei else ("hold" if (b.has_exit and i <= b.exit_hi_i) else "tail"))
            st = rev.minute_state(d, tk, done, files, trees)
            need[(kind, st.split("/")[0])] += 1
            if st == "missing":
                pairs.setdefault((tk, d), set()).add(kind)
    return need, pairs

say("\n## THE FETCH LIST (pairs = ticker|date with minute bars in NO local tree; 'empty' = fetched before, no bars at the source — not re-listed)")
allsets = {"fit": sets["fit_dated"] + sets["fit_und"], "check_2019_2023": sets["chk_dated"] + sets["chk_und"],
           "check_2022H2": sets["chk_dated_2022H2"] + sets["chk_und_2022H2"], "beside_2021_22": sets["beside_dated"] + sets["beside_und"],
           "listed_2017_18": sets["listed_2017"]}
for variant, (warm, tail, noexit) in {"A: warm-up 10 + buy day + hold to exit_hi (no tail; still-held: +20)": (WARM, 0, NOEXIT),
                                       "B: warm-up 10 + hold + 20-session tail (still-held: +20)": (WARM, TAIL, NOEXIT),
                                       "C: hold only (buy day .. exit_hi), no warm-up, no tail": (0, 0, 0)}.items():
    say(f"- variant {variant}")
    union = {}
    for name, bs in allsets.items():
        need, pairs = hold_pairs(bs, warm, tail, noexit)
        for k, v in pairs.items():
            union.setdefault(k, set()).update(v)
        kinds = collections.Counter()
        for k, v in pairs.items():
            for x in v: kinds[x] += 1
        say(f"    {name}: trades {len(bs)}; ticker-days needed {sum(v for k, v in need.items() if isinstance(k, tuple))}; "
            f"missing pairs {len(pairs)} (by kind {dict(kinds)}); already covered {sum(v for k, v in need.items() if isinstance(k, tuple) and k[1] == 'ok')}; "
            f"empty at source {sum(v for k, v in need.items() if isinstance(k, tuple) and k[1] == 'empty')}")
    byy = collections.Counter(d[:4] for (_t, d) in union)
    say(f"    UNION distinct pairs: {len(union)}; by year {dict(sorted(byy.items()))}; distinct dates {len({d for _t, d in union})}")
    if variant.startswith("B"):
        chosen_union = union
    if variant.startswith("A"):
        a_union = union

# the written lists: the three WALKED blocks (fit 2020, the virgin years, 2021-22); 2017-18 and 2020 before 01-27 are listed, never walked
WALKED = {"fit2020": allsets["fit"], "virgin": allsets["check_2019_2023"] + allsets["check_2022H2"] + sets["listed_2020_pre0127"], "y2122": allsets["beside_2021_22"]}
# the virgin block = 2019, 2023, 2022 after the previous check window, and 2020 before the dense window (01-27); 2017-18 listed, never walked
for tag, (warm, tail, noexit) in (("B", (WARM, TAIL, NOEXIT)), ("A", (WARM, 0, NOEXIT))):
    union = {}
    for name, bs in WALKED.items():
        _n, pairs = hold_pairs(bs, warm, tail, noexit)
        for k in pairs:
            union.setdefault(k, set()).add(name)
    rows = sorted(union.items(), key=lambda x: (x[0][1], x[0][0]))
    p = os.path.join(OUT, f"fetch_list_{'' if tag == 'B' else 'hold_only_'}intra_1025.psv")
    with open(p, "w") as fh:
        for (tk, d), blocks in rows:
            fh.write(f"{tk}|{d}|{'+'.join(sorted(blocks))}\n")
    h = hashlib.sha256(open(p, "rb").read()).hexdigest()
    byb = collections.Counter("+".join(sorted(b)) for _k, b in rows)
    byy = collections.Counter(d[:4] for (_t, d), _b in rows)
    say(f"- variant {tag} written {p}: {len(rows)} pairs over {len({d for (_t, d), _b in rows})} dates, sha256 {h}; by block {dict(sorted(byb.items()))}; by year {dict(sorted(byy.items()))}")
    only = {name: sum(1 for _k, b in rows if b == {name}) for name in WALKED}
    say(f"    pairs needed by ONE block only: {only}; fit+virgin without 2021-22: {sum(1 for _k, b in rows if 'y2122' not in b)}")
sets_all_virgin = sets["virgin_all"]
say("\n## THE BRACKETS' CLOCKS (when a 1-minute / 30-minute / later-60-minute level can exist at first_clock)")
FIT, CHK = rev.FIT_WIN, rev.CHECK_WIN
sets = {
    "fit dated 2020 (in-session)": [b for b in inwin(S["dec_used"], FIT) if b.in_bracket],
    "fit undated 2020 nf (in-session)": [b for b in rev.gate_steps(inwin(S["ex_nf"], FIT))[0] if b.in_bracket],
    "fit undated 2020 flickers (in-session)": [b for b in rev.gate_steps(inwin(S["ex_all"], FIT))[0] if b.in_bracket and b.flicker],
    "2021-22 dated (in-session)": [b for b in inwin(S["dec_used"], CHK) if b.in_bracket],
    "2021-22 undated nf (in-session)": [b for b in rev.gate_steps(inwin(S["ex_nf"], CHK))[0] if b.in_bracket],
    "2021-22 undated flickers (in-session)": [b for b in rev.gate_steps(inwin(S["ex_all"], CHK))[0] if b.in_bracket and b.flicker],
    "2019+2023 dated (in-session)": [b for b in S["dec_used"] if b.year in (2019, 2023) and b.in_bracket],
    "2019+2023 undated nf (in-session)": [b for b in rev.gate_steps([b for b in S["ex_nf"] if b.year in (2019, 2023)])[0] if b.in_bracket],
    "2019+2023 undated flickers (in-session)": [b for b in rev.gate_steps([b for b in S["ex_all"] if b.year in (2019, 2023)])[0] if b.in_bracket and b.flicker],
    "2020 before 01-27 (in-session, dated + undated)": [b for b in sets["listed_2020_pre0127"] if b.in_bracket],
    "2022 after 06-14 (in-session)": [b for b in sets["chk_dated_2022H2"] + sets["chk_und_2022H2"] if b.in_bracket],
}
say("set | n | width<=0 | first<09:31 | first<09:35 | first<10:00 | first>=10:00 | flat>=10:00 (bracket wholly after the first 60-min candle) | first>=10:30 | pre-market-flat n")
for k, bs in sets.items():
    fm = [rev.hhmm_to_min(b.first_clock) for b in bs]
    fl = [rev.hhmm_to_min(b.flat_clock) for b in bs]
    w = [f - a for f, a in zip(fm, fl)]
    say(f"{k} | {len(bs)} | {sum(1 for x in w if x <= 0)} (flat before 09:30 by the clock: {sum(1 for x in fl if x < 0)}) | {sum(1 for x in fm if x < 1)} | {sum(1 for x in fm if x < 5)} | {sum(1 for x in fm if x < 30)} | "
          f"{sum(1 for x in fm if x >= 30)} | {sum(1 for x in fl if x >= 30)} | {sum(1 for x in fm if x >= 60)}")
# the held-before-09:35 list with first_clock (ORH1 exists from 09:31)
hb = [b for b in S["dec_used"] + S["used_633"] if b.held_before_0935]
mis = rev.clock_misreads(sn)                      # guard (8) of the previous registration: |raw clock - fitted clock| > 2 min, per video
say(f"misread-clock frames (guard 8): {len(mis)}; by year " + str(dict(collections.Counter(d[:4] for d, _o in mis.values()))))
def sane(b):
    """§2c clock sanity: the flat frame in session by ctx AND by its clock (>= 09:30), a positive width, no misread frame on either end."""
    fl, fm = rev.hhmm_to_min(b.flat_clock), rev.hhmm_to_min(b.first_clock)
    if fl is None or fm is None or fl < 0:
        return "flat_before_open"
    if fm - fl <= 0:
        return "zero_width"
    if b.first_frame in mis or b.prev_full_frame in mis:
        return "clock_misread"
    return "ok"
say("§2c clock sanity per set (in-session windows): ok / flat_before_open / zero_width / clock_misread")
for k, bs in sets.items():
    c = collections.Counter(sane(b) for b in bs)
    say(f"  {k}: n {len(bs)} -> " + ", ".join(f"{r} {c.get(r, 0)}" for r in ("ok", "flat_before_open", "zero_width", "clock_misread")) +
        f"; ok non-flicker {sum(1 for b in bs if sane(b) == 'ok' and not b.flicker)}")
say("held before 09:35: " + str([(b.sym, b.E, b.flat_clock, b.first_clock, "in" if b.in_bracket else ("pre" if b.pre_flat_bracket else "-")) for b in hb]))
# 2019 / 2023 bracket detail
for b in sets["2019+2023 undated nf (in-session)"] + sets["2019+2023 dated (in-session)"] + sets["2019+2023 undated flickers (in-session)"] + sets["2020 before 01-27 (in-session, dated + undated)"]:
    say(f"  virgin bracket: {b.sym} {b.E} {b.setup} {b.flat_clock} -> {b.first_clock} {'flicker' if b.flicker else ''} exit {b.exit_lo} {b.exit_hi}")
vb = [b for b in sets_all_virgin if b.in_bracket]
ok = [b for b in vb if sane(b) == "ok"]
say(f"VIRGIN BLOCK in-session windows {len(vb)} -> scorable after §2c {len(ok)} (non-flicker {sum(1 for b in ok if not b.flicker)}): " +
    ", ".join(f"{b.sym} {b.E}{' (flicker)' if b.flicker else ''}" for b in sorted(ok, key=lambda x: (x.flicker, x.E))))
say("  dropped: " + ", ".join(f"{b.sym} {b.E} {sane(b)}" for b in vb if sane(b) != "ok"))
# exits known / window widths for the virgin dated set (EXIT's check)
vd = [b for b in S["dec_used"] if b.year in (2019, 2023)]
say("virgin dated: " + str([(b.sym, b.E, b.setup, b.exit_lo, b.exit_hi, b.exit_window_len()) for b in vd]))

with open(os.path.join(OUT, "00_pop_fetch.txt"), "w") as fh:
    fh.write("\n".join(lines) + "\n")
print("DONE")
