#!/usr/bin/env python3
"""#711 step 6b -- INDEPENDENT RECOUNT of R1 and R5 (2026-10-31).

Written from the definitions in the pre-registration doc (docs/analysis/cb_asis_reconstruction_prereg_2026-10-26.md, section 4.1 steps
2-6 and section 4.2 R1 / R5) and from the INPUT files only: the reader sheets, windows v2 (entries_v2 / exits_v2), ranges.tsv (step 5's
reachable range per window side), the session calendar and the daily bars.  It imports nothing from asis_common.py / 03_check.py /
asis_check_common.py and it opens neither 03_check.py nor asis_check_common.py.  The published verdict columns of check_r1_r5.tsv
(join_status, primary, inside, r5_agree ...) are NOT read until the very end, where they are diffed against these counts by stmt_id.

Reads only; writes recount.txt beside this file.  No network, nothing dated after 2024-12-31 is used (statements end 2022-04-13).
Run:  python3 recount.py            (prints to stdout and writes recount.txt)
"""
import bisect
import collections
import csv
import gzip
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = "/Users/alvinfung/apollo_data"
OUT = f"{DATA}/cb702/qm_streams/asis_1026"
SHEETS = [f"{OUT}/sheets_filled/reader1_t1_v2_part{p}.tsv" for p in (1, 2, 3)]
ENTRIES = f"{OUT}/windows_v2/entries_v2.tsv"
EXITS = f"{OUT}/windows_v2/exits_v2.tsv"
RANGES = f"{OUT}/ranges.tsv"
SESSIONS = f"{DATA}/cb702_pre_v2/sessions.txt"
EXPORT_A = f"{DATA}/cb702_pre_v2/daily_closes_all.csv.gz"      # sym,date,o,h,l,c,v ; keyed by TODAY's symbol, through 2022-06-30
EXPORT_B = f"{DATA}/cb702/daily_closes_all.csv.gz"             # same columns; symbol of the day, 2021-09-27..
RAW_CLOSE_A = f"{DATA}/cb702_pre_v2/daily_raw_close.csv.gz"    # sym,date,raw close (export A rows)
# published outputs: opened ONLY in the final diff section, and only to diff by stmt_id
PUB_CHECK = f"{OUT}/check_r1_r5.tsv"
PUB_CTRL = f"{OUT}/control_ranges.tsv"
A_LAST = "2022-03-31"      # export A is keyed by today's symbol (bar_sym); after this date the symbol of the day is used (export B)

LINES = []


def P(*a):
    s = " ".join(str(x) for x in a)
    print(s)
    LINES.append(s)


def pct(n, d):
    return "n/a" if d == 0 else f"{100.0 * n / d:.1f}%"


def tsv(path):
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


# ======================================================================================================================================
# 0. INPUT PINS -- the files this recount reads, hashed and set beside the pins of the step-6b re-run
# ======================================================================================================================================
import hashlib


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


PINFILE = os.path.join(HERE, "..", "03_check_pins.txt")          # the pins pasted below the freeze marker (name <TAB> sha256)
PINNED = {}
with open(PINFILE) as fh:
    for ln in fh:
        f = ln.rstrip("\n").split("\t")
        if len(f) == 2:
            PINNED[f[0]] = f[1]
P("## 0. Inputs and their pins (03_check_pins.txt = the step-6b re-run pins in the doc)")
for nm, path in (("reader1_t1_v2_part1", SHEETS[0]), ("reader1_t1_v2_part2", SHEETS[1]), ("reader1_t1_v2_part3", SHEETS[2]), ("entries_v2", ENTRIES),
                 ("exits_v2", EXITS), ("snapshots_v2", f"{OUT}/windows_v2/snapshots_v2.tsv"), ("ranges", RANGES), ("sessions_A", SESSIONS),
                 ("export_A", EXPORT_A), ("export_B", EXPORT_B), ("raw_close_A", RAW_CLOSE_A)):
    h = sha(path)
    pin = PINNED.get(nm)
    P(f"- {nm:<20} {h[:16]}  pin {pin[:16] if pin else 'n/a':<16}  {'MATCH' if pin == h else 'differs (the pin may be on the cut rows, not the file bytes)' if pin else 'no pin'}")
P("")

# ======================================================================================================================================
# 1. STATEMENTS (section 4.1 step 4 labels; section 4.2 R1 input)
# ======================================================================================================================================
P("# #711 step 6b INDEPENDENT RECOUNT -- recount.txt (2026-10-31)")
P("Inputs: reader sheets (3 parts), windows v2, ranges.tsv, sessions.txt, daily export A/B + raw close A.  Published verdict columns not read until section 9.")
P("")
P("## 1. Statements")
ST = []
for p in SHEETS:
    ST += tsv(p)
P(f"- statements in the 3 price-batch sheets: {len(ST)} (unique stmt_id {len(set(r['stmt_id'] for r in ST))})")
OWN = [r for r in ST if r["his_trade"] == "Y"]
P(f"- his own trade (his_trade = Y): {len(OWN)} / {len(ST)}")
tc = collections.Counter(r["ticker_ident"] for r in OWN)
P(f"- of his own trade, ticker identified: Y {tc['Y']}, amb {tc['amb']}, N {tc['N']}")
TY = [r for r in OWN if r["ticker_ident"] == "Y"]
P(f"- own trade + ticker Y: {len(TY)}")
R1IN = [r for r in TY if r["price_stated"] == "Y"]
P(f"- R1 input (own + ticker Y + price stated): {len(R1IN)}   [published 102]")
anyp = [r for r in OWN if r["price_stated"] == "Y"]
tcp = collections.Counter(r["ticker_ident"] for r in anyp)
P(f"- own + price stated at ANY ticker reading: {len(anyp)} = Y {tcp['Y']} + amb {tcp['amb']} + N {tcp['N']}   [published 174 = 102 + 38 + 34]")

# a stated price is a FILL when its kind is entry / exit, a LEVEL when it is a stop or 'other' (doc section 11: the reader labels the kind;
# only fills enter R1); the actions stop_level / result carry a level or a result, not a fill
LEVEL_KINDS = {"stop", "other"}
LEVEL_ACTIONS = {"stop_level", "result"}


def is_level(r):
    return r["price_kind"] in LEVEL_KINDS or r["action"] in LEVEL_ACTIONS


def is_clean(r):
    return r["price_garbled"] != "Y"


P(f"- clean {sum(is_clean(r) for r in R1IN)} / garbled {sum(not is_clean(r) for r in R1IN)}   [published 67 / 35]")
P(f"- fill {sum(not is_level(r) for r in R1IN)} / level {sum(is_level(r) for r in R1IN)}   [published 89 / 13]")
CLEANFILL = [r for r in R1IN if is_clean(r) and not is_level(r)]
P(f"- clean fills: {len(CLEANFILL)}   [published 58]")

# side of an action (doc section 4.2 R5): bought / added / shorted -> a BUY window; stopped / sold / covered -> a SALE window
BUY_ACT = {"buy", "add", "shorted"}
SELL_ACT = {"sell_part", "sell_all", "sell_unspec", "stopped", "covered"}
NO_SIDE = {"holding", "stop_level", "result"}


def act_side(a):
    return "buy" if a in BUY_ACT else "sale" if a in SELL_ACT else None


# the price kind a fill carries on each side: an entry price belongs to a buy-side action, an exit price to a sell-side action
KIND_FOR_SIDE = {"buy": "entry", "sale": "exit"}
matched = [r for r in CLEANFILL if act_side(r["action"]) and r["price_kind"] == KIND_FOR_SIDE[act_side(r["action"])]]
P(f"- of the clean fills, price kind matching the action's side: {len(matched)}  (the other {len(CLEANFILL) - len(matched)}: holding / entry or side-mismatched)   [published 47 / 11]")
NAMED_DAY = {"stream_day", "stated_earlier", "implied_recent"}
matched_named = [r for r in matched if r["date_pinnable"] in NAMED_DAY]
P(f"- of those, day class naming a day (stream_day / stated_earlier / implied_recent): {len(matched_named)}; unstated / approx_earlier: {len(matched) - len(matched_named)}   [published 25 / 22]")

# ======================================================================================================================================
# 2. CALENDAR
# ======================================================================================================================================
P("")
P("## 2. Calendar")
SESS = [l.strip() for l in open(SESSIONS) if l.strip()]
SESSSET = set(SESS)
P(f"- sessions {SESS[0]}..{SESS[-1]}, n {len(SESS)}")
nonsess = sorted(set(r["stream_date"] for r in ST if r["stream_date"] not in SESSSET))
P(f"- price-batch stream dates that are not sessions: {len(nonsess)} {nonsess[:5]}  -> no weekend/holiday convention needed")
P("- statement day = the stream date for EVERY day class (the sheets carry a day CLASS, not a resolved date; 'yesterday' is therefore caught by the one-session tolerance)")


def sidx(d):
    """session index of date d (a window edge is always a session); beyond the calendar -> far away."""
    if d > SESS[-1]:
        return len(SESS) + 1000
    return bisect.bisect_left(SESS, d)


def shift_session(d, k):
    i = sidx(d) + k
    return SESS[i] if 0 <= i < len(SESS) else None


# ======================================================================================================================================
# 3. WINDOWS (section 3.1 / 3.2): buy = (lo, hi) of entries_v2, sale = (exit_lo, exit_hi); keyed on the panel symbol
# ======================================================================================================================================
P("")
P("## 3. Windows v2")
E = tsv(ENTRIES)
X = tsv(EXITS)
P(f"- positions {len(E)} (entries_v2), sale rows {len(X)} (exits_v2)")
POS = {}
WIN = []          # (eid, side, lo, hi)
for e in E:
    eid = int(e["eid"])
    POS[eid] = e
    if e["lo"]:
        WIN.append((eid, "buy", e["lo"], e["hi"]))
    if e["exit_hi"]:
        WIN.append((eid, "sale", e["exit_lo"], e["exit_hi"]))
nb = sum(1 for w in WIN if w[1] == "buy")
ns = sum(1 for w in WIN if w[1] == "sale")
P(f"- windows: buy {nb}, sale {ns}   [published 1,945 / 1,945]")
RG = tsv(RANGES)
RGK = {(int(r["eid"]), r["side"]): r for r in RG}
bad = [(w[0], w[1]) for w in WIN if (w[0], w[1]) not in RGK or RGK[(w[0], w[1])]["lo"] != w[2] or RGK[(w[0], w[1])]["hi"] != w[3]]
P(f"- ranges.tsv rows {len(RG)}; windows whose (lo, hi) disagree with ranges.tsv or are missing there: {len(bad)}")
BYSYM = collections.defaultdict(list)       # panel symbol -> windows
BYSYMA = collections.defaultdict(list)
for w in WIN:
    BYSYM[POS[w[0]]["sym"]].append(w)
    BYSYMA[POS[w[0]]["sym_a"]].append(w)
POSBY = collections.defaultdict(list)
for eid, e in POS.items():
    POSBY[e["sym"]].append(eid)
    if e["sym_a"] != e["sym"]:
        POSBY[e["sym_a"]].append(eid)
RENAMES = {"GSX": "GOTU", "SBE": "CHPT"}


def ba(eid):
    """the export-A / minute-file symbol of a position (keyed by TODAY's symbol): sym_a, with the two rename gaps mapped (GSX -> GOTU, SBE -> CHPT)"""
    return RENAMES.get(POS[eid]["sym_a"], POS[eid]["sym_a"])


def windows_for(tk):
    """the windows of the reader's ticker: panel symbol first, then the bar-file symbol, then the two rename gaps (a data join only)"""
    if tk in BYSYM:
        return BYSYM[tk], "sym"
    if tk in BYSYMA:
        return BYSYMA[tk], "sym_a"
    if tk in RENAMES and RENAMES[tk] in BYSYM:
        return BYSYM[RENAMES[tk]], "rename"
    return [], None


# ======================================================================================================================================
# 4. THE JOIN (section 4.1 step 6): symbol + day only, nearest window of EITHER side within one session, never the action or the price
# ======================================================================================================================================
P("")
P("## 4. The join (symbol and day only)")


def dist_to(day, lo, hi):
    if lo <= day <= hi:
        return 0
    i = sidx(day)
    return sidx(lo) - i if day < lo else i - sidx(hi)


def join(tk, day):
    """-> (status, reason, landed [(eid, side, dist)]) ; status unique / ambiguous / none"""
    ws, how = windows_for(tk)
    if not ws:
        return "none", "not_on_panel", []
    cand = [(w[0], w[1], dist_to(day, w[2], w[3])) for w in ws]
    cand = [c for c in cand if c[2] <= 1]
    if not cand:
        # the name has positions but no window within a session: is the day inside a hold (between a buy window and its sale window)?
        eids = sorted(set(w[0] for w in ws))
        for eid in eids:
            e = POS[eid]
            held_from = e["hi"]                    # the buy window's last session (the position exists after it)
            held_to = e["exit_lo"] if e["exit_hi"] else None
            if held_from and day > held_from and sidx(day) - sidx(held_from) > 1 and (held_to is None or (day < held_to and sidx(held_to) - sidx(day) > 1)):
                return "none", "inside_hold", []
        return "none", "other_date", []
    m = min(c[2] for c in cand)
    best = [c for c in cand if c[2] == m]
    if len(best) == 1:
        return "unique", "", best
    return "ambiguous", "same_position" if len(set(c[0] for c in best)) == 1 else "cross_position", best


JR = {}
for r in TY:
    JR[r["stmt_id"]] = join(r["ticker"], r["stream_date"])
cnt = collections.Counter(v[0] for v in JR.values())
P(f"- own-trade, ticker-identified statements: {len(TY)} -> unique {cnt['unique']} / ambiguous {cnt['ambiguous']} / no window {cnt['none']}   [published 83 / 30 / 81]")
amb = collections.Counter(v[1] for v in JR.values() if v[0] == "ambiguous")
P(f"  - ambiguous: one position's two windows {amb['same_position']}, across positions {amb['cross_position']}   [published 20 of 30]")
noc = collections.Counter(v[1] for v in JR.values() if v[0] == "none")
P(f"  - no window: inside_hold {noc['inside_hold']}, not_on_panel {noc['not_on_panel']}, other_date {noc['other_date']}   [published 41 / 13 / 27]")
r1ids = set(r["stmt_id"] for r in R1IN)
c1 = collections.Counter(JR[i][0] for i in r1ids)
P(f"- of the R1 input ({len(r1ids)}): unique {c1['unique']} / ambiguous {c1['ambiguous']} (one position's two windows {sum(1 for i in r1ids if JR[i][0] == 'ambiguous' and JR[i][1] == 'same_position')}) / no window {c1['none']}   [published 34 / 14 (9) / 54]")
c1n = collections.Counter(JR[i][1] for i in r1ids if JR[i][0] == "none")
P(f"  - R1 input no window: inside_hold {c1n['inside_hold']}, not_on_panel {c1n['not_on_panel']}, other_date {c1n['other_date']}   [published 28 / 6 / 20]")
by_act = collections.Counter(r["action"] for r in TY if JR[r["stmt_id"]][0] == "unique")
P("- uniquely joined by action: " + ", ".join(f"{k} {by_act[k]}" for k in sorted(by_act)) + "   [published add 1, buy 19, covered 6, holding 9, sell_all 1, sell_part 6, sell_unspec 12, shorted 4, stop_level 8, stopped 17]")

# ======================================================================================================================================
# 5. R5 -- side agreement (section 4.2): the action agrees with the side of the window it landed on; bar >= 90%
# ======================================================================================================================================
P("")
P("## 5. R5 side agreement")
R5ROWS = []
excl = 0
for r in TY:
    st, _, landed = JR[r["stmt_id"]]
    if st != "unique":
        continue
    s = act_side(r["action"])
    if s is None:
        excl += 1
        continue
    eid, side, dist = landed[0]
    R5ROWS.append((r, side, dist, s == side))
agree = sum(1 for x in R5ROWS if x[3])
P(f"R5 BAR: {'PASS' if len(R5ROWS) and agree / len(R5ROWS) >= 0.9 else 'FAIL'} -- {agree} / {len(R5ROWS)} = {pct(agree, len(R5ROWS))} agree (bar >= 90%); excluded, no side: {excl}   [published FAIL 48 / 66 = 72.7%; excluded 17]")
for lab, f in (("2020", lambda r: r["stream_date"] < "2021"), ("2021-22", lambda r: r["stream_date"] >= "2021")):
    sub = [x for x in R5ROWS if f(x[0])]
    P(f"  - {lab}: {sum(1 for x in sub if x[3])} / {len(sub)} = {pct(sum(1 for x in sub if x[3]), len(sub))}   [published 2020 41/55, 2021-22 7/11]")
MISS = sorted(x[0]["stmt_id"] for x in R5ROWS if not x[3])
P(f"  - disagreements ({len(MISS)}):")
for x in sorted((x for x in R5ROWS if not x[3]), key=lambda x: (x[0]["stream_date"], x[0]["stmt_id"])):
    r = x[0]
    P(f"      {r['stmt_id']:<18} {r['stream_date']} {r['ticker']:<6} {r['action']:<12} landed {x[1]:<4} dist {x[2]} day class {r['date_pinnable']}")



# ======================================================================================================================================
# 6. R1 -- containment of the stated clean fill prices in the reachable range of the window the statement landed on (section 4.2)
# ======================================================================================================================================
P("")
P("## 6. R1 containment")

# ---- daily bars (export A keyed by today's symbol through 2022-03-31; export B symbol of the day after) -----------------------------------
import pickle
import tempfile
CACHE = os.path.join(tempfile.gettempdir(), "recount_6b_1031_daily_cache.pkl")      # a speed-up only; the script recomputes when it is absent
NEEDA = set(e["sym_a"] for e in POS.values()) | set(RENAMES.values())
NEEDB = set(e["sym"] for e in POS.values())


def load_daily():
    try:
        with open(CACHE, "rb") as fh:
            return pickle.load(fh)
    except Exception:
        pass
    A, B, RAWC = {}, {}, {}
    lo_d, hi_d = "2019-11-01", "2022-06-30"
    with gzip.open(EXPORT_A, "rt") as fh:
        for ln in fh:
            f = ln.split(",")
            if f[0] in NEEDA and lo_d <= f[1] <= hi_d:
                A[(f[0], f[1])] = (float(f[3]), float(f[4]), float(f[5]))        # high, low, close
    with gzip.open(RAW_CLOSE_A, "rt") as fh:
        for ln in fh:
            f = ln.split(",")
            if f[0] in NEEDA and lo_d <= f[1] <= hi_d:
                RAWC[(f[0], f[1])] = float(f[2])
    with gzip.open(EXPORT_B, "rt") as fh:
        for ln in fh:
            f = ln.split(",")
            if f[0] in NEEDB and "2021-09-27" <= f[1] <= hi_d:
                B[(f[0], f[1])] = (float(f[3]), float(f[4]), float(f[5]))
    try:
        with open(CACHE, "wb") as fh:
            pickle.dump((A, B, RAWC), fh)
    except Exception:
        pass
    return A, B, RAWC


DA, DB, DRAW = load_daily()
P(f"- daily bars loaded for the held names, 2019-11..2022-06: export A {len(DA):,} rows, export B {len(DB):,} rows, raw closes {len(DRAW):,}")


def session_range_raw(pos_eid, date, fallback_factor):
    """the daily high-low of the session `date` for the position's name, in RAW price terms (bar-space range times raw/adjusted close)"""
    e = POS[pos_eid]
    if date <= A_LAST:
        bar = DA.get((ba(pos_eid), date))
        rc = DRAW.get((ba(pos_eid), date))
        if bar and rc and bar[2]:
            return (bar[0] - bar[1]) * (rc / bar[2]), "A"
        if bar:
            return (bar[0] - bar[1]) * fallback_factor, "A(row factor)"
        return None, "no bar"
    bar = DB.get((e["sym"], date))
    if bar:
        return (bar[0] - bar[1]) * fallback_factor, "B"
    bar = DA.get((ba(pos_eid), date))
    if bar:
        return (bar[0] - bar[1]) * fallback_factor, "A(late)"
    return None, "no bar"


def tol_for(price, sess_rng):
    return max(0.01 * price, 0.10 * (sess_rng or 0.0), 0.05)


def nearest_session(day, lo, hi):
    """the session of the window lo..hi that is nearest the stated day (the day itself when it lies inside the window).  Section 4.2 says
    'that session's range' without naming the session; the range being tested is the WINDOW's, so the session is one the window spans."""
    return lo if day < lo else hi if day > hi else day


def landed_range(landed):
    eid, side, _ = landed[0]
    r = RGK[(eid, side)]
    if r["range_lo_raw"] == "" or r["range_hi_raw"] == "":
        return None
    return float(r["range_lo_raw"]), float(r["range_hi_raw"]), r


R1ROWS = []     # dicts for every uniquely-joined R1-input statement
for r in R1IN:
    st, why, landed = JR[r["stmt_id"]]
    if st != "unique":
        continue
    eid, side, dist = landed[0]
    rg = landed_range(landed)
    d = {"r": r, "eid": eid, "side": side, "dist": dist, "ranged": rg is not None}
    if rg:
        lo, hi, row = rg
        price = float(r["price_value"])
        fac = float(row["raw_factor"]) if row["raw_factor"] else 1.0
        sr, src = session_range_raw(eid, nearest_session(r["stream_date"], row["lo"], row["hi"]), fac)
        sr_stream, _ = session_range_raw(eid, r["stream_date"], fac)
        tol = tol_for(price, sr)
        tol_stream = tol_for(price, sr_stream)
        d.update(lo=lo, hi=hi, price=price, factor=fac, sess_rng=sr, sess_src=src, tol=tol, tol_stream=tol_stream,
                 inside_stream=(lo - tol_stream <= price <= hi + tol_stream),
                 inside=(lo - tol <= price <= hi + tol), inside_1pct=(lo - max(0.01 * price, 0.05) <= price <= hi + max(0.01 * price, 0.05)),
                 inside_nodtol=(lo <= price <= hi), bracket=row["bracket"], resolution=row["resolution"], in_span=row["in_span"],
                 flicker=row["flicker"], pre_market_possible="pre_market_possible" in row["flags"])
    R1ROWS.append(d)
P(f"- R1 input uniquely joined: {len(R1ROWS)}; landed window has a range: {sum(d['ranged'] for d in R1ROWS)}   [published 34 / 32]")


def is_matched(r):
    s = act_side(r["action"])
    return bool(s) and r["price_kind"] == KIND_FOR_SIDE[s]


def share(rows, key="inside"):
    return sum(1 for d in rows if d[key]), len(rows)


rA = [d for d in R1ROWS if d["ranged"] and is_clean(d["r"]) and not is_level(d["r"])]
P(f"- reading (a) -- section 4.2 LITERAL: clean fills, uniquely joined, landed window ranged: {len(rA)}   [published 17 = 11 primary + 5 holding/entry-or-side-mismatched + 1 unstated/approx day]")
PRIM = [d for d in rA if is_matched(d["r"]) and d["r"]["date_pinnable"] in NAMED_DAY]
POOL = rA                                  # reading (a): the 17 (the controls are derived for all 17; the headline is the 11)
BESIDE_KIND = [d for d in rA if not is_matched(d["r"])]
BESIDE_DAY = [d for d in rA if is_matched(d["r"]) and d["r"]["date_pinnable"] not in NAMED_DAY]
P(f"- reading (b) -- the published narrowing (R85, a module rule BELOW the freeze marker, not frozen section 4.2 text): kind matches the action's side AND the day class names a day: {len(PRIM)}   [published PRIMARY 11]")
P(f"  - beside (a)-only: holding/entry or side-mismatched {len(BESIDE_KIND)}, matched but unstated / approx day {len(BESIDE_DAY)}   [published 5 / 1]")
P(f"  - distinct (position, side, price) among the primary: {len(set((d['eid'], d['side'], d['price']) for d in PRIM))}   [published 11]")

P("")
P("### the 11 primary statements (reading (b)): the landed window, the range, the tolerance, inside")
P(f"  {'stmt':<18} {'date':<10} {'tkr':<5} {'action':<11} {'price':>7} {'side':<4} {'eid':>5} {'bracket':<12} {'res':<10} {'range_raw':<17} {'sess_rng':>8} {'tol':>6} inside  (1%-only / no-tol)")
for d in sorted(PRIM, key=lambda d: (d["r"]["stream_date"], d["r"]["stmt_id"])):
    r = d["r"]
    P(f"  {r['stmt_id']:<18} {r['stream_date']:<10} {r['ticker']:<5} {r['action']:<11} {d['price']:>7} {d['side']:<4} {d['eid']:>5} {d['bracket']:<12} {d['resolution']:<10} "
      f"{d['lo']}-{d['hi']:<9} {('%.3f' % d['sess_rng']) if d['sess_rng'] is not None else 'None':>8} {d['tol']:>6.3f} {str(d['inside']):<6} ({d['inside_1pct']} / {d['inside_nodtol']})")
n_in, n = share(PRIM)
P(f"- REAL containment (primary, reading (b)): {n_in} / {n} = {pct(n_in, n)}   [published 72.7%]")
n_in1, _ = share(PRIM, "inside_1pct")
n_in0, _ = share(PRIM, "inside_nodtol")
P(f"  - tolerance sensitivity: 1%-of-price / $0.05 only {n_in1} / {n}; no tolerance at all {n_in0} / {n}")
nA_in, nA = share(rA)
P(f"- REAL containment, reading (a) (all 17): {nA_in} / {nA} = {pct(nA_in, nA)}")

# ======================================================================================================================================
# 7. CONTROL (b) -- cross-symbol: the same stated price against the window of ANOTHER name he held that same day (section 4.2)
#    Read as: every other position whose window (either side) contains the stated day or lies within one session of it -- the same
#    eligibility the join uses -- one window per position (its nearest), the position's own name excluded.
# ======================================================================================================================================
P("")
P("## 7. Control (b): cross-symbol")


def cross_windows(d):
    """[(eid, side, dist)] -- for every OTHER name (panel symbol) the window the statement's join would land on had the statement been about
    that name: the nearest window of either side within one session of the stated day, kept only when that join is UNIQUE for the name
    (an ambiguous name -- a tie between its windows -- supplies no control window).  The statement's own name is excluded."""
    day = d["r"]["stream_date"]
    own = {POS[d["eid"]]["sym"], POS[d["eid"]]["sym_a"]}
    out = []
    for s in sorted(BYSYM):
        if s in own:
            continue
        st, _, landed = join(s, day)
        if st == "unique":
            out.append(landed[0])
    return sorted(out)


def sess_range_other(eid, day):
    e = POS[eid]
    rg = None
    for side in ("buy", "sale"):
        rr = RGK.get((eid, side))
        if rr and rr["raw_factor"]:
            rg = float(rr["raw_factor"])
            break
    return session_range_raw(eid, day, rg if rg is not None else 1.0)[0]


CROSS = {}
for d in POOL:
    day = d["r"]["stream_date"]
    rows = []
    for (eid, side, ds) in cross_windows(d):
        row = RGK[(eid, side)]
        if row["range_lo_raw"] == "":
            rows.append({"eid": eid, "side": side, "ranged": False})
            continue
        lo, hi = float(row["range_lo_raw"]), float(row["range_hi_raw"])
        sr = sess_range_other(eid, nearest_session(day, row["lo"], row["hi"]))
        tol = tol_for(d["price"], sr)
        rows.append({"eid": eid, "side": side, "ranged": True, "lo": lo, "hi": hi, "tol": tol, "inside": lo - tol <= d["price"] <= hi + tol,
                     "inside_1pct": lo - max(0.01 * d["price"], 0.05) <= d["price"] <= hi + max(0.01 * d["price"], 0.05)})
    CROSS[d["r"]["stmt_id"]] = rows
CROSS_SHARE = {}
for sid, v in CROSS.items():
    rr = [x for x in v if x["ranged"]]
    CROSS_SHARE[sid] = (sum(1 for x in rr if x["inside"]), len(rr))


def cross_stat(group):
    """(mean of per-statement shares in %, statements with a share, pooled inside, pooled windows)"""
    sh = [CROSS_SHARE[d["r"]["stmt_id"]] for d in group]
    ok = [a / b for a, b in sh if b]
    return (100.0 * sum(ok) / len(ok) if ok else None), len(ok), sum(a for a, b in sh), sum(b for a, b in sh)


tot = sum(len(CROSS[d["r"]["stmt_id"]]) for d in PRIM)
rng_n = sum(1 for d in PRIM for x in CROSS[d["r"]["stmt_id"]] if x["ranged"])
P(f"- cross windows over the 11 primary statements: {tot} ({rng_n} ranged); names per statement: " + ", ".join(str(len(CROSS[d['r']['stmt_id']])) for d in PRIM) + "   [published 21, 7, 5, 20, 23, 23, 14, 18, 10, 36, 21 -- compared row by row in section 9]")
for d in PRIM:
    a_, b_ = CROSS_SHARE[d["r"]["stmt_id"]]
    P(f"    {d['r']['stmt_id']:<18} {d['r']['ticker']:<5} {a_} / {b_} other-name windows contain {d['price']}")
m_, n_, pa_, pb_ = cross_stat(PRIM)
P(f"- cross-symbol control share (11 primary): mean of per-statement shares {m_:.1f}% (n {n_} statements); pooled {pa_} / {pb_} = {pct(pa_, pb_)}   [published 5.1% (n 11)]")


# ======================================================================================================================================
# 8. CONTROL (a) -- shifted windows.  The SAME stock's reachable range with the window moved by -3, -2, -1, +1, +2, +3 sessions (section 4.2).
#    Re-derived here from the minute tree and the daily bars, using the section 3.2 bracket table and the frame clocks of windows v2,
#    and then compared edge by edge with control_ranges.tsv (section 9).  No code of step 5/6 is read or used.
# ======================================================================================================================================
P("")
P("## 8. Control (a): shifted windows, re-derived from minute bars")
MIN_ROOTS = [("A", f"{DATA}/cb702_pre_v2/minutes"), ("B", f"{DATA}/cb702/minutes"), ("EP", f"{DATA}/cb702/minutes_ep_1023"),
             ("EP2", f"{DATA}/cb702/minutes_ep_1024"), ("REV", f"{DATA}/cb702/minutes_rev_1024"), ("INTRA", f"{DATA}/cb702/minutes_intra_1025"),
             ("ASIS", f"{DATA}/cb702/minutes_asis_1026")]
_MCACHE = {}


def day_file(root, date):
    key = (root, date)
    if key not in _MCACHE:
        rows = collections.defaultdict(list)
        pth = f"{root}/{date}.psv.gz"
        if os.path.exists(pth):
            with gzip.open(pth, "rt") as fh:
                for ln in fh:
                    f = ln.rstrip("\n").split("|")
                    if len(f) >= 6:
                        try:
                            rows[f[0]].append((int(f[1]), float(f[3]), float(f[4])))      # minute since 09:30, high, low
                        except ValueError:
                            pass
        _MCACHE[key] = rows
    return _MCACHE[key]


def minute_rows(sym, date):
    """first tree (A, B, EP, EP2, REV, INTRA, ASIS) that holds bars for (sym, date); [] when none"""
    for name, root in MIN_ROOTS:
        r = day_file(root, date).get(sym)
        if r:
            return r
    return []


def clock_min(hhmm):
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m) - 570


SNAP = tsv(f"{OUT}/windows_v2/snapshots_v2.tsv")
SNAPID = {s["frame_id"]: s for s in SNAP}


def endpoint_frames(eid, side):
    """(early frame, late frame) of a window: buy = (prev_full_frame, first_frame); sale = (the LAST frame showing the name on exit_lo, exit_frame)"""
    e = POS[eid]
    if side == "buy":
        return SNAPID[e["prev_full_frame"]], SNAPID[e["first_frame"]]
    late = SNAPID[e["exit_frame"]]
    cand = [s for s in SNAP if s["date"] == e["exit_lo"] and int(s["idx"]) < int(late["idx"]) and e["sym"] in s["symbols"].split(",")]
    return (cand[-1] if cand else None), late


def bar_symbol(eid, date):
    return ba(eid) if date <= A_LAST else POS[eid]["sym"]


def factor_at(eid, date, fallback):
    if date <= A_LAST:
        bar, rc = DA.get((ba(eid), date)), DRAW.get((ba(eid), date))
        if bar and rc and bar[2]:
            return rc / bar[2]
    return fallback


def derive_range(eid, side, lo, hi, early, late, variant, daily_only=False):
    """reachable range (raw prices) of the window lo..hi, trimmed by the bracket table: the first session starts at the earlier frame's
    clock when that frame is in-session; the last session ends at the later frame's clock when that frame is in-session ON hi.  A session
    with minute bars uses them; a session without uses its daily bar (flag daily).  Returns (low, high, resolution, flags)."""
    s0, s1 = sidx(lo), sidx(hi)
    sessions = SESS[s0:s1 + 1]
    t_early = clock_min(early["clock"]) if early and early["ctx"] == "in" else None
    t_late = clock_min(late["clock"]) if late and late["ctx"] == "in" and late["date"] == hi else None
    inc_start, inc_end = variant
    lows, highs, kinds, flags = [], [], [], []
    fb = float(RGK[(eid, side)]["raw_factor"]) if RGK[(eid, side)]["raw_factor"] else None      # None: the window carries no raw/adjusted factor
    for s in sessions:
        fac = factor_at(eid, s, fb)
        if fac is None:                 # no daily bar, so no way to convert split-adjusted bars to the prices he saw: the session is unusable
            kinds.append("none")
            continue
        rows = [] if daily_only else minute_rows(bar_symbol(eid, s), s)
        a = (t_early if (s == lo and t_early is not None) else None)
        b = (t_late if (s == hi and t_late is not None) else None)
        sel = rows
        if rows:
            sel = [r for r in rows if (a is None or (r[0] >= a if inc_start else r[0] > a)) and (b is None or (r[0] <= b if inc_end else r[0] < b))]
        if rows and sel:
            lows.append(min(r[2] for r in sel) * fac)
            highs.append(max(r[1] for r in sel) * fac)
            kinds.append("minute")
            continue
        bar = DA.get((ba(eid), s)) if s <= A_LAST else (DB.get((POS[eid]["sym"], s)) or DA.get((ba(eid), s)))
        if bar:
            lows.append(bar[1] * fac)
            highs.append(bar[0] * fac)
            kinds.append("daily")
            if rows and not sel:
                flags.append("clipped")
        else:
            kinds.append("none")
    if not lows:
        return None, None, "none", flags
    res = "minute" if all(k == "minute" for k in kinds) else "daily_only" if all(k != "minute" for k in kinds) else "partial"
    return min(lows), max(highs), res, flags


def shifted_window(lo, hi, k):
    a, b = shift_session(lo, k), shift_session(hi, k)
    return a, b


# the frame endpoints of the 11 landed windows
P(f"- endpoint frames of the 17 landed windows (early frame -> late frame):")
ENDP = {}
for d in POOL:
    eid, side = d["eid"], d["side"]
    early, late = endpoint_frames(eid, side)
    ENDP[(eid, side)] = (early, late)
    ef = f"{early['date']} {early['ctx']} {early['clock']}" if early else "None"
    P(f"    eid {eid:>5} {POS[eid]['sym']:<5} {side:<4} {RGK[(eid, side)]['bracket']:<13} {RGK[(eid, side)]['lo']}..{RGK[(eid, side)]['hi']}   early {ef}  ->  late {late['date']} {late['ctx']} {late['clock']}")

# ---- validate the builder on the 11 REAL landed windows against ranges.tsv (a check on my derivation, not an input to any share) -------
P("- builder check on the 17 real landed windows (my range vs ranges.tsv range_lo_raw / range_hi_raw):")
VARIANTS = [(True, True), (True, False), (False, True), (False, False)]
VBEST = {}
for variant in VARIANTS:
    ok = 0
    for d in POOL:
        eid, side = d["eid"], d["side"]
        rr = RGK[(eid, side)]
        if rr["bracket"] == "sessions_6plus":
            e0, l0 = None, None
        else:
            e0, l0 = ENDP[(eid, side)]
        if rr["bracket"] == "sessions_6plus":
            lo_, hi_, res, fl = derive_range(eid, side, rr["lo"], rr["hi"], None, None, variant)
        else:
            lo_, hi_, res, fl = derive_range(eid, side, rr["lo"], rr["hi"], e0, l0, variant)
        pl, ph = (float(rr["range_lo_raw"]), float(rr["range_hi_raw"])) if rr["range_lo_raw"] else (None, None)
        if lo_ is not None and pl is not None and abs(lo_ - pl) < 0.0051 + 1e-9 and abs(hi_ - ph) < 0.0051 + 1e-9:
            ok += 1
    P(f"    variant start-inclusive={variant[0]} end-inclusive={variant[1]}: {ok} / {len(POOL)} real windows reproduced to the cent")

# ---- the cross-symbol windows' edges re-derived the same way (so the cross control does not rest on ranges.tsv alone) -----------------------------
def rederive(eid, side):
    """my range for a window as it stands (no shift), by the bracket label of ranges.tsv; None when the window has no reachable minutes"""
    rr = RGK[(eid, side)]
    br = rr["bracket"]
    if br == "inverted":
        return None, None, "none", []
    if br == "sessions_6plus":
        return derive_range(eid, side, rr["lo"], rr["hi"], None, None, (True, True), daily_only=True)
    if br == "next_other":
        return derive_range(eid, side, rr["lo"], rr["hi"], None, None, (True, True))        # section 3.2 bracket_other: the full sessions lo..hi
    early, late = endpoint_frames(eid, side)
    return derive_range(eid, side, rr["lo"], rr["hi"], early, late, (True, True))


XW = sorted(set((x["eid"], x["side"]) for d in POOL for x in CROSS[d["r"]["stmt_id"]]))
xok, xbad, xnone = 0, [], 0
for (eid, side) in XW:
    rr = RGK[(eid, side)]
    lo_, hi_, res, fl = rederive(eid, side)
    if rr["range_lo_raw"] == "":
        if lo_ is None:
            xnone += 1
        else:
            xbad.append((eid, side, "published has no range; mine", round(lo_, 4), round(hi_, 4)))
        continue
    if lo_ is not None and abs(lo_ - float(rr["range_lo_raw"])) <= 0.0051 and abs(hi_ - float(rr["range_hi_raw"])) <= 0.0051:
        xok += 1
    else:
        xbad.append((eid, side, rr["bracket"], rr["resolution"], (rr["range_lo_raw"], rr["range_hi_raw"]), (None if lo_ is None else round(lo_, 4), None if hi_ is None else round(hi_, 4)), res, fl))
P(f"- cross-symbol windows (distinct, over the 17): {len(XW)}; edges re-derived from minute / daily bars identical to the cent to ranges.tsv: {xok}; both without a range: {xnone}; differ: {len(xbad)}")
for z in xbad:
    P(f"      DIFF cross window {z}")
P("")
# ---- the shifted windows themselves ---------------------------------------------------------------------------------------------------
KS = (-3, -2, -1, 1, 2, 3)


def daily_range_raw(eid, s):
    bar = DA.get((ba(eid), s)) if s <= A_LAST else (DB.get((POS[eid]["sym"], s)) or DA.get((ba(eid), s)))
    if not bar:
        return None
    fb = float(RGK[(eid, d_side_of[eid])]["raw_factor"]) if RGK[(eid, d_side_of[eid])]["raw_factor"] else 1.0
    return (bar[0] - bar[1]) * factor_at(eid, s, fb)


d_side_of = {d["eid"]: d["side"] for d in POOL}
SHIFT = {}      # stmt_id -> [rows]
for d in POOL:
    eid, side = d["eid"], d["side"]
    rr = RGK[(eid, side)]
    early, late = ENDP[(eid, side)]
    rows = []
    for k in KS:
        a, b = shifted_window(rr["lo"], rr["hi"], k)
        if rr["bracket"] == "sessions_6plus":
            lo_, hi_, res, fl = derive_range(eid, side, a, b, None, None, (True, True), daily_only=True)    # section 3.5: 6+ sessions = daily resolution only
        else:
            # a shifted window keeps its bracket: the same clocks on the moved dates
            lo_, hi_, res, fl = derive_range(eid, side, a, b, early, {"ctx": late["ctx"], "date": b if late["ctx"] == "in" else late["date"], "clock": late["clock"]}, (True, True))
        row = {"k": k, "lo_d": a, "hi_d": b, "lo": lo_, "hi": hi_, "res": res, "flags": fl}
        if lo_ is not None:
            price = d["price"]
            stated_k = shift_session(d["r"]["stream_date"], k)
            cand = {
                "nearest session": daily_range_raw(eid, nearest_session(stated_k, a, b)) if stated_k else None,
                "stated-day+k": daily_range_raw(eid, stated_k) if stated_k else None,
                "first session": daily_range_raw(eid, a),
                "last session": daily_range_raw(eid, b),
                "max over window": max([daily_range_raw(eid, s) or 0 for s in SESS[sidx(a):sidx(b) + 1]] or [0]),
            }
            for nm, sr in list(cand.items()) + [("1%/$0.05 only", None)]:
                tol = tol_for(price, sr)
                row["in:" + nm] = (lo_ - tol <= price <= hi_ + tol)
            row["tol_first"] = tol_for(price, cand["nearest session"])
            row["in"] = row["in:nearest session"]
        rows.append(row)
    SHIFT[d["r"]["stmt_id"]] = rows
n_ranged = sum(1 for v in SHIFT.values() for x in v if x["lo"] is not None)
P(f"- shifted windows derived: {sum(len(v) for v in SHIFT.values())} (102 expected = 17 x 6); with a range {n_ranged}")

P("")
P("### shifted-window control: the share of the 6 shifted windows that contain the stated price, per statement")
TOLS = ["nearest session", "stated-day+k", "first session", "last session", "max over window", "1%/$0.05 only"]


def shift_stat(group, tol="nearest session"):
    """(mean of per-statement shares in %, inside, windows)"""
    sh, ia, nb_ = [], 0, 0
    for d in group:
        rows = [x for x in SHIFT[d["r"]["stmt_id"]] if x["lo"] is not None]
        a_ = sum(1 for x in rows if x["in:" + tol])
        sh.append(a_ / len(rows))
        ia += a_
        nb_ += len(rows)
    return 100.0 * sum(sh) / len(sh), ia, nb_


for d in POOL:
    sid = d["r"]["stmt_id"]
    rows = [x for x in SHIFT[sid] if x["lo"] is not None]
    P(f"    {sid:<18} {d['r']['ticker']:<5} {d['price']:>7} {'PRIMARY' if d in PRIM else 'beside '} inside {sum(1 for x in rows if x['in'])}/{len(rows)}   by shift k: " +
      " ".join(f"{x['k']:+d}:{'Y' if x['in'] else 'n'}" for x in SHIFT[sid]))
P("- SHIFTED control (11 primary; mean of per-statement shares, every statement has all six windows), by how 'that session's range' is read for the tolerance:")
for t in TOLS:
    m_, ia_, nb_ = shift_stat(PRIM, t)
    P(f"    [{t}] {ia_} / {nb_} = {m_:.1f}%" + ("   [published 47.0% (n 11)]" if t == TOLS[0] else ""))


# ======================================================================================================================================
# 9. DIFF against the published rows, by stmt_id (the first and only place the published verdict columns are opened)
# ======================================================================================================================================
P("")
P("## 9. Diff against the published rows (check_r1_r5.tsv, control_ranges.tsv), by stmt_id")
PUB = {r["stmt_id"]: r for r in tsv(PUB_CHECK)}
PUBC = tsv(PUB_CTRL)
diffs = []

# (a) the join, all 194
dj = []
for r in TY:
    sid = r["stmt_id"]
    st, why, landed = JR[sid]
    p = PUB[sid]
    mine = (st, why if st == "none" else "", str(landed[0][0]) if st == "unique" else "", landed[0][1] if st == "unique" else "", str(landed[0][2]) if st == "unique" else "")
    pub = (p["join_status"], p["join_reason"] if p["join_status"] == "none" else "", p["eid"] if p["join_status"] == "unique" else "", p["side"] if p["join_status"] == "unique" else "", p["dist"] if p["join_status"] == "unique" else "")
    if mine != pub:
        dj.append((sid, mine, pub))
P(f"- (a) the join, {len(TY)} statements: {len(TY) - len(dj)} identical (status, reason, eid, side, dist); {len(dj)} differ")
for x in dj:
    P(f"      DIFF {x}")
# ambiguous tie sets
dt = 0
for r in TY:
    sid = r["stmt_id"]
    st, why, landed = JR[sid]
    if st == "ambiguous":
        mine = ";".join(sorted(f"{e}:{s}" for e, s, _ in landed))
        pub = ";".join(sorted(PUB[sid]["tied"].split(";")))
        if mine != pub:
            dt += 1
            P(f"      DIFF tie set {sid}: mine {mine} published {pub}")
P(f"  - ambiguous tie sets: {sum(1 for v in JR.values() if v[0] == 'ambiguous') - dt} / {sum(1 for v in JR.values() if v[0] == 'ambiguous')} identical")

# (b) R5
d5 = []
for (r, side, dist, ok) in R5ROWS:
    p = PUB[r["stmt_id"]]
    if (p["r5_agree"] == "True") != ok:
        d5.append(r["stmt_id"])
pub5 = set(k for k, p in PUB.items() if p["r5_agree"] in ("True", "False"))
mine5 = set(x[0]["stmt_id"] for x in R5ROWS)
P(f"- (b) R5: population mine {len(mine5)} vs published {len(pub5)} (set-equal {mine5 == pub5}); agree/disagree differs on {len(d5)} rows; "
  f"disagreement sets mine {len(MISS)} vs published {sum(1 for p in PUB.values() if p['r5_agree'] == 'False')}, set-equal {set(MISS) == set(k for k, p in PUB.items() if p['r5_agree'] == 'False')}")

# (c) the primary set
pubprim = set(k for k, p in PUB.items() if p["primary"] == "True")
mineprim = set(d["r"]["stmt_id"] for d in PRIM)
P(f"- (c) primary set: mine {len(mineprim)} vs published {len(pubprim)}; set-equal {mineprim == pubprim}  (only mine: {sorted(mineprim - pubprim)}; only published: {sorted(pubprim - mineprim)})")
# reading (a) rows and the published clean-fill ranged rows
pubA = set(k for k, p in PUB.items() if p["fill"] == "fill" and p["garbled"] == "False" and p["join_status"] == "unique" and p["range_lo_raw"] != "")
P(f"  - reading (a) set (17): mine vs published clean/fill/unique/ranged: set-equal {set(d['r']['stmt_id'] for d in rA) == pubA}")
# (d) per-row real containment
dd = []
for d in rA:
    p = PUB[d["r"]["stmt_id"]]
    mine = (d["inside"], round(d["tol"], 3), round(d["lo"], 4), round(d["hi"], 4), round(d["sess_rng"], 3))
    pub = (p["inside"] == "True", round(float(p["tolerance"]), 3), round(float(p["range_lo_raw"]), 4), round(float(p["range_hi_raw"]), 4), round(float(p["session_range_raw"]), 3))
    if mine != pub:
        dd.append((d["r"]["stmt_id"], mine, pub))
P(f"- (d) real containment rows (17): {len(rA) - len(dd)} identical on (inside, tolerance, range lo, range hi, session range); {len(dd)} differ")
for x in dd:
    P(f"      DIFF {x}")

# (e) shifted windows: edges and inside, 66 rows
PUBS = collections.defaultdict(dict)
for r in PUBC:
    if r["control"] == "shifted":
        PUBS[r["stmt_id"]][int(r["k"])] = r
de, dtol, din, nres = [], [], [], []
for d in POOL:
    sid = d["r"]["stmt_id"]
    for x in SHIFT[sid]:
        p = PUBS[sid][x["k"]]
        if p["lo"] != x["lo_d"] or p["hi"] != x["hi_d"]:
            de.append((sid, x["k"], "dates", (x["lo_d"], x["hi_d"]), (p["lo"], p["hi"])))
        if x["res"] != p["resolution"]:
            nres.append((sid, x["k"], x["res"], p["resolution"]))
        if abs(x["lo"] - float(p["range_lo_raw"])) > 0.0051 or abs(x["hi"] - float(p["range_hi_raw"])) > 0.0051:
            de.append((sid, x["k"], "edges", (round(x["lo"], 4), round(x["hi"], 4)), (p["range_lo_raw"], p["range_hi_raw"])))
        if abs(x["tol_first"] - float(p["tolerance"])) > 0.0011:
            dtol.append((sid, x["k"], round(x["tol_first"], 4), p["tolerance"]))
        if x["in"] != (p["inside"] == "True"):
            din.append((sid, x["k"], x["in"], p["inside"]))
P(f"- (e) shifted windows (102 = 17 x 6): dates identical on {102 - sum(1 for z in de if z[2] == 'dates')}; edges identical to the cent on {102 - sum(1 for z in de if z[2] == 'edges')}; "
  f"resolution identical on {102 - len(nres)}; tolerance (nearest-session rule) identical on {102 - len(dtol)}; inside identical on {102 - len(din)}")
for z in de + nres + dtol + din:
    P(f"      DIFF {z}")

# (f) cross: window sets and inside
dcs, dci = [], []
pubcross = collections.defaultdict(dict)
for r in PUBC:
    if r["control"] == "cross":
        pubcross[r["stmt_id"]][(int(r["eid"]), r["side"])] = r
for d in POOL:
    sid = d["r"]["stmt_id"]
    mine = {(x["eid"], x["side"]): x for x in CROSS[sid]}
    pub = pubcross[sid]
    if set(mine) != set(pub):
        dcs.append((sid, sorted(set(mine) - set(pub)), sorted(set(pub) - set(mine))))
    for key in set(mine) & set(pub):
        pr, mr = pub[key], mine[key]
        if (pr["inside"] == "") != (not mr["ranged"]):
            dci.append((sid, key, "ranged", mr["ranged"], pr["inside"]))
        elif mr["ranged"] and ((pr["inside"] == "True") != mr["inside"] or abs(float(pr["tolerance"]) - mr["tol"]) > 0.0011):
            dci.append((sid, key, "inside/tol", (mr["inside"], round(mr["tol"], 4)), (pr["inside"], pr["tolerance"])))
P(f"- (f) cross-symbol windows: per-statement window sets identical on {17 - len(dcs)} / 17 statements; row-level (ranged, inside, tolerance) differs on {len(dci)} rows")
for z in dcs + dci:
    P(f"      DIFF {z}")


# ======================================================================================================================================
# 10. THE RECOUNT -- R1 and R5 as the doc defines them, beside the published numbers
# ======================================================================================================================================
P("")
P("## 10. The recount")


def r1_line(label, group, pub):
    n = len(group)
    if not n:
        P(f"  {label:<20} n 0")
        return None
    ins = sum(1 for d in group if d["inside"])
    sh, _, _ = shift_stat(group)
    cr, ncr, _, _ = cross_stat(group)
    real = 100.0 * ins / n
    g1, g2 = real - sh, real - cr
    mine = (n, round(real, 1), round(sh, 1), round(cr, 1), round(g1, 1), round(g2, 1))
    same = (mine == pub) if pub else None
    P(f"  {label:<20} n {n:<3} inside {ins}/{n} = {real:.1f}%   shifted {sh:.1f}%   cross {cr:.1f}%   gap shifted {g1:.1f}   gap cross {g2:.1f}   "
      f"{'[published ' + ' / '.join(str(x) for x in pub) + (' -- identical]' if same else ' -- DIFFERS]') if pub else ''}")
    return mine


PUB_R1 = {"all": (11, 72.7, 47.0, 5.1, 25.8, 67.6), "2020": (9, 66.7, 38.9, 4.9, 27.8, 61.8), "2021-22": (2, 100.0, 83.3, 6.1, 16.7, 93.9),
          "without flickers": (9, 77.8, 46.3, 6.2, 31.5, 71.5), "flickers only": (2, 50.0, 50.0, 0.0, 0.0, 50.0),
          "without daily-only": (8, 75.0, 37.5, 5.5, 37.5, 69.5), "daily-only only": (3, 66.7, 72.2, 4.1, -5.6, 62.6)}
P("R1 containment (the primary = reading (b), 11 statements; real share, shifted-window share, cross-symbol share, gaps in points):")
res_all = r1_line("all", PRIM, PUB_R1["all"])
allsame = [res_all == PUB_R1["all"]]
for lab, f in (("2020", lambda d: d["r"]["stream_date"] < "2021"), ("2021-22", lambda d: d["r"]["stream_date"] >= "2021"),
               ("without flickers", lambda d: d["flicker"] != "True"), ("flickers only", lambda d: d["flicker"] == "True"),
               ("without daily-only", lambda d: d["resolution"] != "daily_only"), ("daily-only only", lambda d: d["resolution"] == "daily_only")):
    allsame.append(r1_line(lab, [d for d in PRIM if f(d)], PUB_R1[lab]) == PUB_R1[lab])
n_prim = len(PRIM)
g_sh, g_cr = res_all[4], res_all[5]
verdict = "NOT DECIDABLE" if n_prim < 100 else ("PASS" if g_sh >= 25 and g_cr >= 25 else "FAIL")
would = "PASS" if g_sh >= 25 and g_cr >= 25 else "FAIL"
P(f"R1 GAP BAR: {verdict} (primary n {n_prim} < the section 9 floor of 100); gaps {g_sh:.1f} over the shifted-window control, {g_cr:.1f} over the cross-symbol control (bar >= 25 each); would read {would} at a decidable n   [published: NOT DECIDABLE, 25.8 / 67.6, would read PASS]")
P(f"  - margin on the shifted bar: {shift_stat(PRIM)[1]} / {shift_stat(PRIM)[2]} shifted windows contain the price; ONE more window inside makes the gap {100 * 8 / 11 - 100 * (shift_stat(PRIM)[1] + 1) / 66:.1f} (under the bar); the 1%-only tolerance reads 30 / 66 = gap {100 * 8 / 11 - 100 * 30 / 66:.1f}")
m17 = r1_line("reading (a), all 17", POOL, None)
P(f"  - reading (a) (the literal section 4.2 population, 17 clean fills): n 17 < 100 -> NOT DECIDABLE as well; would read {'PASS' if m17[4] >= 25 and m17[5] >= 25 else 'FAIL'}")

# sensitivity (first-pass reading of 'the window of another name he held that day'): EVERY other position's nearest eligible window, ties kept
#   (a name whose windows tie, or two positions of one name, then contribute several windows).  Tolerance as in the main reading.
def loose_cross(d):
    day = d["r"]["stream_date"]
    own = {POS[d["eid"]]["sym"], POS[d["eid"]]["sym_a"]}
    per_pos = collections.defaultdict(list)
    for (eid, side, lo, hi) in WIN:
        if POS[eid]["sym"] in own or POS[eid]["sym_a"] in own:
            continue
        ds = dist_to(day, lo, hi)
        if ds <= 1:
            per_pos[eid].append((eid, side, ds))
    out = []
    for eid, lst in per_pos.items():
        m_ = min(x[2] for x in lst)
        out += [x for x in lst if x[2] == m_]
    return out


shares_loose, pa_l, pb_l = [], 0, 0
for d in PRIM:
    ins_, n_ = 0, 0
    for (eid, side, ds) in loose_cross(d):
        row = RGK[(eid, side)]
        if row["range_lo_raw"] == "":
            continue
        lo, hi = float(row["range_lo_raw"]), float(row["range_hi_raw"])
        tol = tol_for(d["price"], sess_range_other(eid, nearest_session(d["r"]["stream_date"], row["lo"], row["hi"])))
        n_ += 1
        ins_ += 1 if lo - tol <= d["price"] <= hi + tol else 0
    shares_loose.append(ins_ / n_ if n_ else None)
    pa_l += ins_
    pb_l += n_
okl = [x for x in shares_loose if x is not None]
P(f"  - sensitivity, cross control read loosely (every other position's nearest window, ties kept): {100 * sum(okl) / len(okl):.1f}% (mean of {len(okl)} per-statement shares; pooled {pa_l} / {pb_l}) -> gap {100 * 8 / 11 - 100 * sum(okl) / len(okl):.1f}; same verdict")

P("")
P("R5 side agreement (unique joins with an action that has a side):")
PUB_R5 = {"all": (48, 66), "2020": (41, 55), "2021-22": (7, 11), "without flickers": (43, 57), "flickers only": (5, 9), "without daily-only": (44, 61), "daily-only only": (4, 5)}


def landed_row(r):
    return RGK[(JR[r["stmt_id"]][2][0][0], JR[r["stmt_id"]][2][0][1])]


R5_ALL = []
for lab, f in (("all", lambda r: True), ("2020", lambda r: r["stream_date"] < "2021"), ("2021-22", lambda r: r["stream_date"] >= "2021"),
               ("without flickers", lambda r: landed_row(r)["flicker"] != "True"), ("flickers only", lambda r: landed_row(r)["flicker"] == "True"),
               ("without daily-only", lambda r: landed_row(r)["resolution"] != "daily_only"), ("daily-only only", lambda r: landed_row(r)["resolution"] == "daily_only")):
    sub = [x for x in R5ROWS if f(x[0])]
    a_, b_ = sum(1 for x in sub if x[3]), len(sub)
    same = (a_, b_) == PUB_R5[lab]
    R5_ALL.append(same)
    P(f"  {lab:<20} {a_} / {b_} = {pct(a_, b_)}   [published {PUB_R5[lab][0]} / {PUB_R5[lab][1]} -- {'identical' if same else 'DIFFERS'}]")
P(f"R5 BAR: {'PASS' if agree / len(R5ROWS) >= 0.9 else 'FAIL'} -- {agree} / {len(R5ROWS)} = {pct(agree, len(R5ROWS))} (bar >= 90%)   [published FAIL 48 / 66 = 72.7%]")
# sensitivity: the join over ticker-ambiguous statements as well (a guessed symbol -- NOT in the registered population)
amb_rows = [r for r in OWN if r["ticker_ident"] == "amb"]
ag2, n2 = 0, 0
for r in amb_rows:
    st, _, landed = join(r["ticker"], r["stream_date"]) if r["ticker"] else ("none", "", [])
    if st == "unique" and act_side(r["action"]):
        n2 += 1
        ag2 += 1 if act_side(r["action"]) == landed[0][1] else 0
P(f"  - sensitivity, not the bar: if the {len(amb_rows)} ticker-AMBIGUOUS own-trade statements (a guessed symbol) were joined too, {n2} more would place uniquely with a side and {ag2} of them agree -> {agree + ag2} / {len(R5ROWS) + n2} = {pct(agree + ag2, len(R5ROWS) + n2)}")

P("")
rowlevel_ok = (not dj and not dd and not de and not nres and not dtol and not din and not dcs and not dci and not d5 and mineprim == pubprim and not xbad)
P("MATCH: " + ("YES -- every count, every verdict and every row-level cell compared reproduces the published run" if (all(allsame) and all(R5_ALL) and rowlevel_ok) else "NO -- see DIFF lines above"))
P(f"  - R1 lines identical {sum(allsame)} / {len(allsame)}; R5 lines identical {sum(R5_ALL)} / {len(R5_ALL)}; row-level differences: join {len(dj)}, R5 {len(d5)}, real containment {len(dd)}, shifted {len(de) + len(nres) + len(dtol) + len(din)}, cross {len(dcs) + len(dci)}, re-derived cross edges {len(xbad)}")

with open(os.path.join(HERE, "recount.txt"), "w", encoding="utf-8") as fh:
    fh.write("\n".join(LINES) + "\n")
