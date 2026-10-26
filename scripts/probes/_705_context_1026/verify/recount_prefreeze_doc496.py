#!/usr/bin/env python3
"""Independent pre-freeze recount of docs/analysis/cb_context_rules_prereg_2026-10-26.md (REGISTERED, NOT FROZEN, NOT RUN).

The registration is NOT edited. Nothing from any frozen module is imported or executed - the frozen rule-mix module is read as TEXT
(constants, the LIBRARY tuple, function names) and by sha256 only. The rule-mix recounts are not imported (they execute at import).

OUTCOME-FREE. Reads ONLY:
  - the holdings timeline's entries.tsv (the `setup` label, `era`, the buy day);
  - the rule-mix per-trade tag files (tags_enter / tags_stop / tags_exit): HEADER lines, the label / offset columns (block, dated, flicker,
    tagged, status, room, loser, exit_lo_j, exit_hi_j, flat_clock, first_clock, era) and - as a printout cross-check, the doc itself does not
    read them before the freeze - the `*_bucket` / `*_booked_j` / `tag` columns, tallied into the shares the rule-mix printout already
    prints. No price bar, minute bar or outcome is opened; no context value is computed; no map is scored; no bucket is crossed with
    any context.
  - the rule-mix tag printout (01_mix_tag.txt), the intraday / reverse printouts, operator_shared_notes.md (quotes + line cites),
    the rule-mix and earlier registrations (as text), the frozen module as TEXT, the minute trees' fetch logs (_done.psv) and the fetch
    list (membership only; NO bar file of any tree is opened).
Nothing dated after 2024-12-31 (asserted); replay/ and his_exits/ are never opened.

Output: one line per claim `[Ldoc] label | doc | mine | OK / MISMATCH / NOTE`; the MISMATCH lines are listed again at the end.
"""
import collections
import datetime
import hashlib
import math
import os
import re
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
DATA = "/Users/alvinfung/apollo_data"
H = f"{DATA}/cb702/qm_streams/holdings_1024/"
RM = H + "rule_mix/"
OUT_TXT = os.path.join(HERE, "recount_prefreeze.txt")
DOC = os.path.join(REPO, "docs", "analysis", "cb_context_rules_prereg_2026-10-26.md")
P_MIX = os.path.join(REPO, "scripts", "probes", "_705_rule_mix_1025")
P_INT = os.path.join(REPO, "scripts", "probes", "_705_intraday_1025")
P_REV = os.path.join(REPO, "scripts", "probes", "_705_reverse_1024")
F_TAG = os.path.join(P_MIX, "01_mix_tag.txt")
F_MIXMOD = os.path.join(P_MIX, "01_mix_frozen_75c832541cef.py")
F_INTMOD = os.path.join(P_INT, "01_intra_frozen_ac598fc58aae.py")
F_NOTES = os.path.join(REPO, "docs", "methodology", "operator_shared_notes.md")
F_MIXDOC = os.path.join(REPO, "docs", "analysis", "cb_rule_mix_prereg_2026-10-25.md")
F_REVDOC = os.path.join(REPO, "docs", "analysis", "cb_reverse_engineer_his_rules_prereg_2026-10-24.md")
F_INTDOC = os.path.join(REPO, "docs", "analysis", "cb_intraday_layer_prereg_2026-10-25.md")
F_REVCHK = os.path.join(P_REV, "01_rev_check.txt")
F_TREND = os.path.join(REPO, "scripts", "probes", "_702_race_1022", "03_market_trend_split.py")
F_REPLAY = os.path.join(REPO, "scripts", "probes", "_705_qm_replay_1023", "01_replay.py")
F_MIXPINS = os.path.join(P_MIX, "01_mix_pins.txt")
D_BODIES = os.path.join(P_MIX, "freeze_bodies")
INTRA_MIN = f"{DATA}/cb702/minutes_intra_1025"
LIST_FULL = f"{INTRA_MIN}/fetch_list_intra_1025.psv"
TREES = {"A": f"{DATA}/cb702_pre_v2/minutes", "B": f"{DATA}/cb702/minutes", "EP": f"{DATA}/cb702/minutes_ep_1023",
         "EP2": f"{DATA}/cb702/minutes_ep_1024", "REV": f"{DATA}/cb702/minutes_rev_1024"}
TREE_ORDER = ("A", "B", "EP", "EP2", "REV")
CUT = "2024-12-31"
A_LAST = "2022-03-31"

LINES, CLAIMS = [], []
DOC_TOKEN_WARN = []
UNRESOLVED = []
DL = open(DOC, encoding="utf8").read().splitlines()
PL = open(F_TAG, encoding="utf8").read().splitlines()


def say(msg=""):
    print(msg, flush=True)
    LINES.append(msg)


def LN(anchor):
    for i, ln in enumerate(DL, 1):
        if anchor in ln:
            return i
    UNRESOLVED.append(anchor)
    return "?"


def fmt(x):
    if isinstance(x, (list, tuple, dict, set)):
        return str(x)
    if isinstance(x, (float, np.floating)):
        return f"{x:.4g}"
    return str(x)


def claim(at, label, doc, mine, kind=None, note="", tok=True):
    """doc / mine compared as printed text. kind None -> OK if equal else MISMATCH; 'OK' / 'MISMATCH' forced; 'NOTE' informational.
    `at` = a doc line number, '--' (not a doc claim) or '@anchor' (the first doc line containing the anchor text)."""
    if isinstance(at, str) and at.startswith("@"):
        at = LN(at[1:])
    status = ("OK" if fmt(doc) == fmt(mine) else "MISMATCH") if kind is None else kind
    if isinstance(at, int) and kind != "NOTE" and tok:
        win = " ".join(DL[max(0, at - 4):at + 2]).replace(",", "")
        toks = re.findall(r"\d+(?:\.\d+)?", str(doc).replace(",", ""))
        lost = [t for t in toks if t not in win]
        if lost:
            DOC_TOKEN_WARN.append((at, label, str(doc), lost))
    CLAIMS.append((at, label, doc, mine, status, note))
    say(f"[L{at}] {label} | doc {fmt(doc)} | mine {fmt(mine)} | {status}" + (f" | {note}" if note else ""))


def pp(line):
    """percent tokens of a printout line, as floats"""
    return [float(x) for x in re.findall(r"(\d+(?:\.\d+)?)%", line)]


def cells(line):
    return [c.strip() for c in line.split("|")]


def plain(s):
    """notes text normalised: markdown marks, leading list / quote markers, curly quotes and line breaks removed"""
    s = s.replace("“", '"').replace("”", '"').replace("’", "'")
    s = re.sub(r"\*+", "", s)
    return re.sub(r"\s+", " ", s).strip()


def notes_span(a, b):
    out = []
    for ln in NOTES[a - 1:b]:
        out.append(re.sub(r"^\s*(>|-)\s*", "", ln))
    return plain(" ".join(out))


def rd(path):
    return pd.read_csv(path, sep="\t", dtype=str, keep_default_na=False)


say("# #705 CONTEXT-RULES registration: independent pre-freeze recount (OUTCOME-FREE: timeline TSV, tag-file labels / offsets / bucket tallies, printout lines)")
say("# registration: docs/analysis/cb_context_rules_prereg_2026-10-26.md (not edited); no frozen module imported or run (read as text + sha only)")
say()

# ======================================================================================================== inputs
E = rd(H + "entries.tsv")
TE, TS, TX = rd(RM + "tags_enter.tsv"), rd(RM + "tags_stop.tsv"), rd(RM + "tags_exit.tsv")
NOTES = open(F_NOTES, encoding="utf8").read().splitlines()
say(f"- inputs: doc {len(DL)} lines; tag printout {len(PL)} lines; entries {len(E):,} rows; tags_enter {len(TE)} / tags_stop {len(TS)} / tags_exit {len(TX)} rows; notes {len(NOTES)} lines")
setup_of = dict(zip(E.eid, E.setup))
for nm, t in (("enter", TE), ("stop", TS), ("exit", TX)):
    t["setup"] = t.eid.map(setup_of)
    assert t.setup.notna().all()
    assert (t.E <= CUT).all(), f"{nm}: a buy day after {CUT}"
say(f"- every buy day in the three tag files <= {CUT}: asserted (max {max(TE.E.max(), TS.E.max(), TX.E.max())})")

# ============================================================================================ 0. label sanity
say("\n## 0. The labels the doc's populations rest on (dated = the timeline's setup in breakout / EP / both; era by buy day)")
for nm, t in (("tags_enter", TE), ("tags_stop", TS), ("tags_exit", TX)):
    bad = int(((t.dated == "True") != t.setup.isin(["breakout", "EP", "both"])).sum())
    claim("@dated = our tl breakout or EP gap day fired", f"{nm}: rows where `dated` disagrees with setup in {{breakout, EP, both}}", 0, bad, tok=False)
for nm, t in (("tags_stop", TS), ("tags_exit", TX)):
    bad = int(((t.era == "A") != (t.E <= A_LAST)).sum())
    claim("@era B = `cb702` cut at 2024-12-31", f"{nm}: rows where era A != (buy day <= {A_LAST})", 0, bad, tok=False,
          note=f"era A {int((t.era == 'A').sum())} / B {int((t.era == 'B').sum())}")
claim("@dated = our tl breakout or EP gap day fired", "tag files' `setup` ∈ {breakout, EP, both} <=> dated: values seen among dated rows",
      "breakout / EP / both", " / ".join(sorted(set(TE[TE.dated == 'True'].setup) | set(TS[TS.dated == 'True'].setup) | set(TX[TX.dated == 'True'].setup), key=lambda s: ['breakout', 'EP', 'both'].index(s))))

# ============================================================================== 1. the scorable sets (§2 table)
say("\n## 1. §2 table: the scorable sets recounted from the tag files; the cited printout line's `n scorable` re-read")
BLK = ("2020", "2021-22", "untouched")
ENT = TE[TE.tagged == "True"]
STP = TS[(TS.status == "scorable") & (TS.room == "True") & (TS.loser == "True")]
EXT = TX[(TX.status == "scorable") & (TX.room == "True")]
SETS = {"ENTER": ENT, "STOP": STP, "EXIT": EXT}


def split3(df):
    c = df.setup.value_counts()
    return f"{c.get('breakout', 0)} / {c.get('EP', 0)} / {c.get('both', 0)}"


# parse the doc's own §2 table so nothing here is my transcription of the doc
tbl = []
i0 = LN("| decision | block | n | setup within dated")
assert isinstance(i0, int)
for k in range(i0 + 1, len(DL)):
    if not DL[k].startswith("|"):
        break
    if set(DL[k].replace("|", "").strip()) <= set("-: "):
        continue
    tbl.append((k + 1, [c.strip() for c in DL[k].strip().strip("|").split("|")]))
claim(i0, "§2 table: data rows parsed from the doc", 10, len(tbl), tok=False)
nrows = {}
for ln, c in tbl:
    dec = re.sub(r"[*]", "", c[0]).split()[0]
    blk = c[1]
    m = re.search(r"\*\*(\d+)\*\*\s*\((\d+)\s*\+\s*(\d+)\)", c[2])
    if c[0].startswith("ENTER beside"):
        # undated flickers beside
        fl = [int(x) for x in re.findall(r"\d+", c[2])]
        mine = [int(((TE.block == b) & (TE.flicker == "True") & (TE.dated == "False")).sum()) for b in BLK]
        claim(ln, "ENTER beside: undated flickers 2020 / 2021-22 / untouched (flicker & not dated)", fl, mine)
        srcs = [int(x) for x in re.findall(r"l\.(\d+)", c[4])]
        for b, s_, n_ in zip(BLK, srcs, fl):
            claim(ln, f"ENTER beside {b}: printout line {s_} header 'n scorable'", n_, int(re.search(r"n scorable (\d+)", PL[s_ - 1]).group(1)),
                  note=PL[s_ - 1][:70])
        continue
    n_doc, d_doc, u_doc = int(m.group(1)), int(m.group(2)), int(m.group(3))
    sub = SETS[dec][SETS[dec].block == blk]
    mine_n, mine_d, mine_u = len(sub), int((sub.dated == "True").sum()), int((sub.dated == "False").sum())
    claim(ln, f"{dec} {blk}: n scorable (dated + undated)", f"{n_doc} ({d_doc} + {u_doc})", f"{mine_n} ({mine_d} + {mine_u})")
    nrows[(dec, blk)] = n_doc
    if c[3] not in ("—", "-"):
        claim(ln, f"{dec} {blk}: setup within dated (breakout / EP / both)", c[3], split3(sub[sub.dated == "True"]))
    src = int(re.search(r"l\.(\d+)", c[4]).group(1))
    pr = int(re.search(r"n scorable (\d+)", PL[src - 1]).group(1))
    claim(ln, f"{dec} {blk}: printout l.{src} header `n scorable`", n_doc, pr, note=PL[src - 1][:80])

# dated / undated sub-block headers the doc does not cite by line (and the ones it does: STOP l.312, 337, 389, 414)
for dec in ("ENTER", "STOP", "EXIT"):
    for blk in BLK:
        for lab, dd in (("dated", "True"), ("undated", "False")):
            pref = f"decision {dec} — block {blk} / {lab}"
            hits = [(i + 1, l) for i, l in enumerate(PL) if l.startswith(pref)]
            sub = SETS[dec][(SETS[dec].block == blk) & (SETS[dec].dated == dd)]
            if hits:
                n_pr = int(re.search(r"n scorable (\d+)", hits[0][1]).group(1))
                claim("--", f"{dec} {blk} {lab}: printout sub-block header (l.{hits[0][0]}) `n scorable` vs tag-file count", n_pr, len(sub))
            else:
                claim("--", f"{dec} {blk} {lab}: no sub-block header printed; tag-file count", "n/a", len(sub), kind="NOTE")
for l_, want in ((312, "STOP — block 2020 / dated"), (337, "STOP — block 2020 / undated"), (389, "STOP — block 2021-22 / dated"), (414, "STOP — block 2021-22 / undated")):
    claim("@01_mix_tag.txt` l.312, l.337, l.389, l.414", f"header: printout l.{l_} is the STOP sub-block named", want, re.sub(r"^decision ", "", PL[l_ - 1])[:len(want)], tok=False)

say("\n## 1b. §2 notes: no_room counts, the EP-too-small line, the floors")
nr_e = [int(((TX.block == b) & (TX.status == "scorable") & (TX.room == "False")).sum()) for b in BLK]
nr_s = [int(((TS.block == b) & (TS.status == "scorable") & (TS.room == "False") & (TS.loser == "True")).sum()) for b in BLK]
claim("@every other `no_room` trade in control (a)", "no_room trades in control (a): EXIT 2020 / 2021-22 / untouched", "97 / 92 / 28", " / ".join(map(str, nr_e)))
claim("@every other `no_room` trade in control (a)", "no_room trades in control (a): STOP losers 2020 / 2021-22 / untouched", "56 / 57 / 14", " / ".join(map(str, nr_s)))
for l_, b, ne, ns in zip((285, 362, 439), BLK, (97, 92, 28), (56, 57, 14)):
    claim("@every other `no_room` trade in control (a)", f"printout l.{l_} {b}: 'no_room in (a)' / 'no_room trades beside' (STOP header)", f"{ne} / {ns}",
          f"{re.search(r'no_room in .a. (\d+)', PL[l_ - 1]).group(1)} / {re.search(r'no_room trades beside (\d+)', PL[l_ - 1]).group(1)}")
for l_, b, ne in zip((540, 650, 760), BLK, (97, 92, 28)):
    claim("@every other `no_room` trade in control (a)", f"printout l.{l_} {b}: EXIT header 'no_room in (a)'", ne, int(re.search(r"no_room in .a. (\d+)", PL[l_ - 1]).group(1)))
ex20 = EXT[(EXT.block == "2020") & (EXT.dated == "True")]
en20 = ENT[(ENT.block == "2020") & (ENT.dated == "True")]
ep_en = int(en20.setup.isin(["EP", "both"]).sum())
ep_ex = int(ex20.setup.isin(["EP", "both"]).sum())
claim("@EP is too small for its own group", "EP (EP + both) among 2020 dated ENTER windows / dated exits", "5 of 31 / 19 of 122", f"{ep_en} of {len(en20)} / {ep_ex} of {len(ex20)}")
m_floor = {d: max(15, math.ceil(0.10 * n)) for d, n in (("ENTER", 88), ("STOP", 139), ("EXIT", 333))}
claim("@ENTER 15, STOP 15, EXIT 34", "m = max(15, ceil(0.10 × n_2020)) with n_2020 from the tag files", "ENTER 15, STOP 15, EXIT 34",
      ", ".join(f"{d} {max(15, math.ceil(0.10 * len(SETS[d][SETS[d].block == '2020'])))}" for d in ("ENTER", "STOP", "EXIT")))
claim("@EP is too small for its own group", "both EP counts are under the leaf floors (5 < 15 ENTER; 19 < 34 EXIT)", "yes", "yes" if ep_en < 15 and ep_ex < 34 else "no")

# ====================================================================================== 2. tree counts, candidate splits
say("\n## 2. §5c: candidate splits, tree counts (derived by enumerating the §5b tree grammar, not the formula), libraries, tiers")
CTX_SPLITS = {"ENTER": {"C-E1": 2, "C-E2": 1, "C-E3": 1, "C-E4": 1}, "STOP": {"C-S1": 3, "C-S2": 2, "C-S3": 1, "C-S4": 1},
              "EXIT": {"C-X1": 2, "C-X2": 2, "C-X3": 2, "C-X4": 1, "C-X5": 1}}


def count_trees(s):
    """depth <= 2: no split; one split with two group children; one split whose two children are each a group or one further split
    (further split = any of the s candidate (context, cut) pairs). Enumerate explicitly."""
    n = 1  # no split
    for _root in range(s):
        for left in range(s + 1):          # s splits + 1 'group'
            for right in range(s + 1):
                n += 1
    return n


claim("@Candidate splits: ENTER 5", "candidate splits ENTER / STOP / EXIT (cut candidates summed per context, from the §3 tables)", "5 / 7 / 8",
      " / ".join(str(sum(CTX_SPLITS[d].values())) for d in ("ENTER", "STOP", "EXIT")))
claim("@Trees before the floor", "trees before the floor (enumerated): ENTER / STOP / EXIT", "181 / 449 / 649",
      " / ".join(str(count_trees(sum(CTX_SPLITS[d].values()))) for d in ("ENTER", "STOP", "EXIT")))
claim("@Trees before the floor", "closed form 1 + s + s·((s+1)² − 1) at s = 5 / 7 / 8", "181 / 449 / 649",
      " / ".join(str(1 + s + s * ((s + 1) ** 2 - 1)) for s in (5, 7, 8)))
# the §3 tables, parsed from the doc: cut candidates per context
sec3 = "\n".join(DL[LN("## 3. THE CONTEXTS"):LN("## 4. \"CLOSE TO\"")])
parsed = {}
for m in re.finditer(r"^\| (C-[ESX]\d) \| [^|]*\| [^|]*\| [^|]*\| ([^|]*) \|", sec3, flags=re.M):
    parsed[m.group(1)] = 1 if "binary" in m.group(2) else len(m.group(2).split(","))
expect = {k: v for d in CTX_SPLITS.values() for k, v in d.items()}
claim("@Candidate splits: ENTER 5", "cut candidates per context, parsed from the doc's own §3 tables (the 'cut candidates' column)", str(expect), str(parsed))

# the library, from the frozen module's text
mod = open(F_MIXMOD, encoding="utf8").read()
lib = {}
for dec in ("ENTER", "STOP", "EXIT"):
    a = mod.index(f'"{dec}": (', mod.index("LIBRARY = {"))
    b = mod.index("\n    ),", a)
    lib[dec] = [(m.group(1), int(m.group(2))) for m in re.finditer(r'Rule\("[^"]+", "([^"]+)", "[^"]*", (\d), ', mod[a:b])]
claim("@5a. The rules a group may take", "library sizes ENTER / STOP / EXIT (frozen module text)", "7 / 15 / 12", " / ".join(str(len(lib[d])) for d in ("ENTER", "STOP", "EXIT")), tok=False)
claim("@5a. The rules a group may take", "ENTER library order", "L1, L8, L2, L7, L3, L9, L4", ", ".join(c for c, _ in lib["ENTER"]))
claim("@5a. The rules a group may take", "STOP library order (doc: 'S1-T … S4-C')", "S1-T … S4-C", f"{lib['STOP'][0][0]} … {lib['STOP'][-1][0]}")
claim("@5a. The rules a group may take", "EXIT library order", "M-1, M-2, M-3, M-4, M-5, M-9, M-6, M-2s, M-11, M-7, M-8, M-10", ", ".join(c for c, _ in lib["EXIT"]))
claim("@`mix|rlevel|{eid}|{d}|{i}`, k = 15", "k-level draws: k = 15 STOP / 12 EXIT = the library sizes", "15 / 12", f"{len(lib['STOP'])} / {len(lib['EXIT'])}")
claim("@MAP-T1, his words only", "tier-1 ENTER rules (MAP-T1)", "L1, L8, L2, L7, L3", ", ".join(c for c, t in lib["ENTER"] if t == 1))
claim("@MAP-T1, his words only", "tier-1 EXIT rules (MAP-T1)", "M-1, M-2, M-3, M-4, M-5, M-9, M-6, M-2s, M-11", ", ".join(c for c, t in lib["EXIT"] if t == 1))
claim("@STOP has one tier-1 cell", "tier-1 STOP cells", "S1-T (1)", f"{', '.join(c for c, t in lib['STOP'] if t == 1)} ({sum(1 for _, t in lib['STOP'] if t == 1)})")
for c in ("SEED = fz.SEED", "DRAWS = 200", 'K_KEY = "mix|rprice|{eid}|{d}|{i}"', 'SHARED_KEY = "mix|bracket|{eid}|{d}"', 'RLEVEL_KEY = "mix|rlevel|{eid}|{d}"',
          'RLEVEL_K_KEY = "mix|rlevel|{eid}|{d}|{i}"'):
    claim("@seed 702, key", f"frozen rule-mix module defines `{c}`", "present", "present" if c in mod else "ABSENT")
claim("@seed 702, key", "frozen intraday module: SEED = 702 and rng_for(key, seed=SEED)", "702", "702" if re.search(r"^SEED = 702", open(F_INTMOD).read(), re.M) else "other")
for fn in ("bucket", "bucket_vec", "random_windows", "random_level_draws", "touch_path", "touch_buckets_vec", "enter_one", "exit_fires", "stop_fire",
           "mix_pins", "tag_lock", "mix_stage_outputs", "mix_dry_run_complete"):
    claim("@Imports the FROZEN rule-mix module", f"frozen rule-mix module defines `{fn}`", "present", "present" if re.search(rf"^def {fn}\(", mod, re.M) else "ABSENT")
for nm in ("DOC", "P_DRY", "LEDGER", "OUT_DIR"):
    claim("@Imports the FROZEN rule-mix module", f"frozen rule-mix module defines the path default `{nm}`", "present", "present" if re.search(rf"^{nm} = ", mod, re.M) else "ABSENT")
imod = open(F_INTMOD, encoding="utf8").read()
for fn in ("rng_for", "fnum", "smas_for", "range_verdict"):
    claim("@`fnum`, `IdCache`, `smas_for`", f"frozen intraday module defines `{fn}`", "present", "present" if re.search(rf"^def {fn}\(", imod, re.M) else "ABSENT")
claim("@`fnum`, `IdCache`, `smas_for`", "frozen intraday module defines `IdCache`", "present", "present" if re.search(r"^class IdCache", imod, re.M) else "ABSENT")
claim("@`Fire`", "frozen rule-mix module defines `class Fire`", "present", "present" if re.search(r"^class Fire", mod, re.M) else "ABSENT")
rev = open(os.path.join(P_REV, "01_rev_frozen_e908253f7405.py"), encoding="utf8").read()
claim("@`rev.adr20_at(bars, e − 1, b)`", "frozen reverse module defines `adr20_at(bars, p, b)` (the doc: rev.adr20_at(bars, e − 1, b))", "present", "present" if re.search(r"^def adr20_at\(bars, p: int, b: Buy\)", rev, re.M) else "ABSENT")

# ===================================================================== 3. shares and unions: tag files vs printouts vs the doc
say("\n## 3. §0 / §9 / §11 G2: standalone shares, BEST, UNION recounted from the tag files' bucket columns and the printout lines")
RUL = {d: [c for c, _ in lib[d]] for d in lib}
share = {}
for d in ("ENTER", "STOP", "EXIT"):
    for b in BLK:
        x = SETS[d][SETS[d].block == b]
        n = len(x)
        sa = {r: int((x[r + "_bucket"] == "EXPLAINS").sum()) for r in RUL[d]}
        best = max(RUL[d], key=lambda r: (sa[r], -RUL[d].index(r)))
        share[(d, b)] = dict(n=n, sa=sa, best=best, union=round(100 * float((x.tag != "discretion").mean()), 1))


def pct(c, n):
    return f"{100 * c / n:.1f}%"


for d, b, rule, want in (("ENTER", "2020", "L1", "36.4%"), ("ENTER", "2021-22", "L1", "43.3%"), ("STOP", "2020", "S1-T", "45.3%"),
                         ("STOP", "2021-22", "S1-T", "44.8%"), ("EXIT", "2020", "M-8", "30.9%"), ("EXIT", "2021-22", "M-8", "27.9%")):
    s = share[(d, b)]
    claim("@Known already", f"{d} {b}: {rule} standalone share (tag file EXPLAINS ÷ n)", want, pct(s["sa"][rule], s["n"]), note=f"{s['sa'][rule]} / {s['n']}")
for d, rule in (("ENTER", "L1"), ("STOP", "S1-T"), ("EXIT", "M-8")):
    claim("@Known already", f"{d} 2020: BEST single rule = argmax of standalone EXPLAINS (ties -> library order)", rule, share[(d, "2020")]["best"])
for d, rule in (("ENTER", "L1"), ("STOP", "S1-T")):
    claim("@Known already", f"{d} 2021-22: the 2020-chosen {rule} is also the block's own best (argmax)", rule, share[(d, "2021-22")]["best"])
x2122 = share[("EXIT", "2021-22")]
claim("@2021-22's own best is M-2 28.4%", "EXIT 2021-22: ORACLE-1 (the block's own argmax) = M-2 at 28.4%; the 2020-chosen M-8 sits at 27.9%", "M-2 28.4% / M-8 27.9%",
      f"{x2122['best']} {pct(x2122['sa'][x2122['best']], 229)} / M-8 {pct(x2122['sa']['M-8'], 229)}")
for l_, d, b, rule in ((50, "ENTER", "2020", "L1"), (146, "ENTER", "2021-22", "L1"), (289, "STOP", "2020", "S1-T"), (366, "STOP", "2021-22", "S1-T"),
                       (554, "EXIT", "2020", "M-8"), (664, "EXIT", "2021-22", "M-8"), (655, "EXIT", "2021-22", "M-2")):
    c = cells(PL[l_ - 1])
    claim("@Known already", f"printout l.{l_} is the {rule} row; its standalone cell = tag-file share", re.match(r"[\d.]+%", c[3]).group(0), pct(share[(d, b)]["sa"][rule], share[(d, b)]["n"]),
          note=f"row '{c[0]}', cell '{c[3]}'")
# unions
for d, vals in (("ENTER", ((("2020", "56.8%"), ("2021-22", "66.7%")), 58, 154)), ("STOP", ((("2020", "54.0%"), ("2021-22", "57.8%")), 305, 382)),
                ("EXIT", ((("2020", "71.5%"), ("2021-22", "72.9%")), 557, 667))):
    (pairs, l20, l2122) = vals
    for (b, want), l_ in zip(pairs, (l20, l2122)):
        claim("@Known already", f"{d} {b}: UNION (1 - discretion) from the tag file vs printout l.{l_}", want, f"{share[(d, b)]['union']}%",
              note=f"printout: {re.search(r'UNION ([\d.]+%)', PL[l_ - 1]).group(1)}")
        claim("@Known already", f"printout l.{l_} UNION value", want, re.search(r"UNION ([\d.]+%)", PL[l_ - 1]).group(1))
e50 = pp(PL[280])
claim("@ENTER's union 56.8% / 66.7% of his", "§0 ENTER: union vs random prices (printout l.281)", "56.8 / 66.7 vs 49.9 / 52.0", f"{e50[0]} / {e50[2]} vs {e50[1]} / {e50[3]}")
s_ = pp(PL[533])
claim("@ENTER's union 56.8% / 66.7% of his", "§0 STOP: union vs random-level line (printout l.534)", "54.0 / 57.8 vs 61.9 / 64.7", f"{s_[0]} / {s_[2]} vs {s_[1]} / {s_[3]}")
x_ = pp(PL[884])
claim("@ENTER's union 56.8% / 66.7% of his", "§0 EXIT: union vs random sell windows (printout l.885)", "71.5 / 72.9 vs 69.8 / 70.9", f"{x_[0]} / {x_[2]} vs {x_[1]} / {x_[3]}")
claim("@never carried", "§0 header: the lines are 'under' for STOP on both blocks", "54.0 < 61.9 and 57.8 < 64.7", f"{s_[0]} < {s_[1]} and {s_[2]} < {s_[3]}")
claim("@Known already", "§9 room over BEST at ±0 on 2020: UNION − BEST for ENTER / STOP / EXIT (doc: about 20 / 9 / 41 points)", "20 / 9 / 41",
      " / ".join(f"{round(share[(d, '2020')]['union'] - 100 * share[(d, '2020')]['sa'][r] / share[(d, '2020')]['n'])}" for d, r in (("ENTER", "L1"), ("STOP", "S1-T"), ("EXIT", "M-8"))),
      note=" / ".join(f"{share[(d, '2020')]['union'] - 100 * share[(d, '2020')]['sa'][r] / share[(d, '2020')]['n']:.1f}" for d, r in (("ENTER", "L1"), ("STOP", "S1-T"), ("EXIT", "M-8"))))
claim("@the rule-mix union beat control (a) by only", "§9 EXIT union over control (a) 'without frames' at ±0: 2020 / 2021-22 (printout l.557 / l.667)", "1.7 / 2.0",
      f"{pp(PL[556])[0] - pp(PL[556])[4]:.1f} / {pp(PL[666])[0] - pp(PL[666])[4]:.1f}", note="UNION minus control (a) 'without frames' (the larger arm), printout l.557 / l.667")
# chance lines cited in §1 / §6 / §9 / §11
c74, c90 = re.search(r"k-price ([\d.]+%)", PL[73]).group(1), re.search(r"k-price ([\d.]+%)", PL[89]).group(1)
claim("@random-price chance of the ENTER union is 59.9%", "§1c: ENTER 2020 k-price union chance, dated l.74 / undated l.90", "59.9% / 44.5%", f"{c74} / {c90}")
r332, r357 = re.search(r"random level \(k = 15\) ([\d.]+%)", PL[331]).group(1), re.search(r"random level \(k = 15\) ([\d.]+%)", PL[356]).group(1)
claim("@random-price chance of the ENTER union is 59.9%", "§1c: STOP 2020 random-level union chance, dated l.332 / undated l.357", "75.1% / 55.0%", f"{r332} / {r357}")
k75 = re.search(r"k-price standalone per rule: L1 ([\d.]+%)", PL[74]).group(1)
k91 = re.search(r"k-price standalone per rule: L1 ([\d.]+%)", PL[90]).group(1)
claim("@k-price floor 23.6% dated vs 19.5% undated", "§6c: per-rule k-price floor (L1) 2020 dated l.75 / undated l.91", "23.6% / 19.5%", f"{k75} / {k91}")
claim("@per-rule random-price floor 20.8% / 30.9%", "§9: L1 random-price chance 2020 l.50 / 2021-22 l.146", "20.8% / 30.9%", f"{cells(PL[49])[4]} / {cells(PL[145])[4]}")
claim("@(2020: L1 k-price 21.0%, l.59, and shared window 3.1%, l.50", "§11 G5: L1 k-price standalone (l.59) / shared-window chance (l.50, 'shifted per level / shared window' second value)", "21.0% / 3.1%",
      f"{re.search(r'k-price standalone per rule: L1 ([\d.]+%)', PL[58]).group(1)} / {cells(PL[49])[5].split('/')[1].strip()}")
c289, c554 = cells(PL[288]), cells(PL[553])
claim("@S1-T control (a) 30.0% / 31.5%", "§11 G5: S1-T control (a) frames / no frames, and the random-level floor (l.289)", "30.0% / 31.5% and 40.4%", f"{c289[4]} and {c289[5]}")
claim("@M-8 control (a) 28.7% / 28.7%", "§11 G5: M-8 control (a) frames / no frames, and the random-level floor (l.554)", "28.7% / 28.7% and 23.6%", f"{c554[4]} and {c554[5]}")
claim("@L1 k-price 21.0%, l.59", "§11 G5: 'and the same rows on 2021-22' - the 2021-22 S1-T / M-8 / L1 rows exist at l.366 / l.664 / l.146", "present", "present" if all(("S1-T" in PL[365], "M-8" in PL[663], "L1" in PL[145])) else "ABSENT")
claim("@the open first by construction, union 100%", "§2: pre-market-flat windows: UNION at printout l.122 / l.138 (doc: 100%)", "100% / 100%", f"{round(float(re.search(r'UNION ([\d.]+)%', PL[121]).group(1)))}% / {round(float(re.search(r'UNION ([\d.]+)%', PL[137]).group(1)))}%")
claim("@43 ORH5 fills", "§3b: fill_orh5_too_wide at printout l.9", 43, int(re.search(r"fill_orh5_too_wide (\d+)", PL[8]).group(1)))
fs = TS.fill_src.value_counts()
claim("@43 ORH5 fills", "§3b: tag file `fill_src` = orh5_too_wide over all STOP records (the printout's fill_orh5_too_wide) / all of them on dated rows", "43 / all dated",
      f"{int(fs.get('orh5_too_wide', 0))} / {'all dated' if (TS[TS.fill_src == 'orh5_too_wide'].dated == 'True').all() else 'NOT all dated'}")
claim("@43 ORH5 fills", "§3b: fill sources add to the 837 records (orh5 + too_wide + close_proxy + open) and match printout l.9 (219 / 43 / 23 / 552)", "219 / 43 / 23 / 552 = 837",
      f"{int(fs.get('orh5', 0))} / {int(fs.get('orh5_too_wide', 0))} / {int(fs.get('close_proxy', 0))} / {int(fs.get('open', 0))} = {int(fs.sum())}", tok=False)
def _set(x):
    return "{" + ", ".join(sorted(set(x))) + "}"


claim("@dated and undated trades carry different fills", "§1c / §3b: fill source by dated: dated rows -> orh5 / orh5_too_wide / close_proxy only; undated rows -> open only",
      "dated {close_proxy, orh5, orh5_too_wide}; undated {open}", f"dated {_set(TS[TS.dated == 'True'].fill_src)}; undated {_set(TS[TS.dated == 'False'].fill_src)}", tok=False)
need_cols = ["block", "dated", "flicker", "tagged", "flat_clock", "first_clock"]
claim("@HEADER LINES and their label and offset columns only", "tags_enter columns the header paragraph names (block, dated, flicker, tagged, buy-day clocks)", "all present",
      "all present" if all(c in TE.columns for c in need_cols) else f"missing {[c for c in need_cols if c not in TE.columns]}")
need_cols2 = ["block", "dated", "status", "room", "loser", "exit_lo_j", "exit_hi_j"]
claim("@HEADER LINES and their label and offset columns only", "tags_stop / tags_exit columns the header paragraph names (block, dated, status, room, loser, exit_lo_j, exit_hi_j)", "all present",
      "all present" if all(c in t.columns for t in (TS, TX) for c in need_cols2) else "missing")
claim("@19,470 pairs", "§10: INTRA log rows at printout l.8", "19,470", re.search(r"INTRA ([\d,]+) log rows", PL[7]).group(1))
claim("@85.9% hit-or-ballpark on the 41 undated", "§4b / §13 Q1: random price hit-or-ballpark on the 41 undated 2021-22 windows (printout l.24)", "85.9% on 41", f"{re.search(r'hit-or-ballpark ([\d.]+%)', PL[23]).group(1)} on {re.search(r'on the previous (\d+) undated', PL[23]).group(1)}")
chk = open(F_REVCHK, encoding="utf8").read()
claim("@85.9% hit-or-ballpark on the 41 undated", "§4b: 01_rev_check.txt carries the control hit-or-ballpark 85.9%", "85.9%", re.search(r"hit-or-ballpark ([\d.]+%) on the deciding set", chk).group(1))

# ===================================================================== 4. offsets, clocks, dates
say("\n## 4. §1f / §4a / §1h / §9: sell-window widths, exit_lo_j, bracket widths, buy dates (labels and offsets only)")


def mins(c):
    h, m = c.split(":")
    return int(h) * 60 + int(m)


def one_sess(df, b):
    x = df[df.block == b]
    w = x.exit_hi_j.astype(float) - x.exit_lo_j.astype(float) + 1
    return int((w == 1).sum()), len(x)


for d, df, doc in (("EXIT", EXT, "231 of 333 / 165 of 229"), ("STOP", STP, "108 of 139 / 80 of 116")):
    a, b2 = one_sess(df, "2020"), one_sess(df, "2021-22")
    claim("@One-session sell windows are 231 of 333", f"one-session sell windows, {d} 2020 / 2021-22", doc, f"{a[0]} of {a[1]} / {b2[0]} of {b2[1]}")
lo20 = EXT[EXT.block == "2020"].exit_lo_j.astype(float)
claim("@exit_lo_j median 3", "§1f: exit_lo_j median / quartiles (EXIT 2020 scorable)", "3 / 1-9", f"{lo20.median():g} / {lo20.quantile(.25):g}-{lo20.quantile(.75):g}")
loall = EXT.exit_lo_j.astype(float)
claim("@exit_lo_j median 3", "§1f: exit_lo_j median / quartiles (EXIT, all three blocks - the doc does not name the base)", "3 / 1-9", f"{loall.median():g} / {loall.quantile(.25):g}-{loall.quantile(.75):g}", kind="NOTE",
      note="same on both bases; EXIT 2021-22 alone is 3 / 1-8")
claim("@a median window start at session 4", "§4a: 'median window start at session 4' = exit_lo_j 3 with the buy day = session 1 (offset 0)", "session 4", f"session {int(lo20.median()) + 1}")
TE2 = TE.copy()
TE2["w"] = TE2.first_clock.map(mins) - TE2.flat_clock.map(mins)
nf = TE2[(TE2.tagged == "True") & (TE2.flicker == "False")]
sc_ = TE2[TE2.tagged == "True"]
claim("@in-session bracket median 27 minutes on 2020", "§4b: in-session NON-FLICKER bracket median minutes, 2020 / 2021-22", "27 / 46",
      " / ".join(f"{nf[nf.block == b].w.median():g}" for b in ("2020", "2021-22")), note=f"n {len(nf[nf.block == '2020'])} / {len(nf[nf.block == '2021-22'])}")
claim("@(median 27", "§1h: same sentence read on the ENTER SCORABLE set (the map's set; includes the dated flickers), 2020 / 2021-22", "27 / 46",
      " / ".join(f"{sc_[sc_.block == b].w.median():g}" for b in ("2020", "2021-22")), kind="NOTE",
      note=f"§1h gives no base; §4b says non-flicker windows and that base matches; on the scorable set the medians are as shown (n {len(sc_[sc_.block == '2020'])} / {len(sc_[sc_.block == '2021-22'])})")
e20 = ENT[ENT.block == "2020"]
mo = e20.E.str[5:7].astype(int)
claim("@2020 buys Feb-May: 30 of 88 by date", "§9: 2020 scorable ENTER buys dated Feb-May", "30 of 88", f"{int(((mo >= 2) & (mo <= 5)).sum())} of {len(e20)}")
claim("@30 of 88 by date", "§9: first / last 2020 scorable ENTER buy dates (for the Feb-May proxy)", "info", f"{e20.E.min()} / {e20.E.max()}", kind="NOTE")
claim("@(g) **Small n.**", "§1g: a 10-point margin on n = 60", "6 trades", f"{round(0.10 * 60)} trades")
half = (30.8, 55.9)
se_pts = (half[1] - half[0]) / 2 / 1.96
claim("@a 10-point margin is 6 trades, about one standard error", "§1g: 'about one standard error' - the printed L1 2021-22 interval [30.8%, 55.9%] (n 60) gives SE (points) / SE (trades) / margin in SEs", "~1 SE",
      f"{se_pts:.1f} pts / {se_pts * 0.6:.1f} trades / {10 / se_pts:.2f} SE", kind="NOTE",
      note="one proportion's SE; a paired MAP-vs-BEST difference has its own SE that depends on how many trades the two disagree on (not countable before the run)")

# ===================================================================== 5. quotes and cites into the notes
say("\n## 5. his words: each quoted string at the cited notes lines")
DOCN = plain(" ".join(DL))
# (anchor, first notes line, last notes line, text as the NOTES have it, text as the DOC quotes it: None = same, "skip" = the doc paraphrases)
Q = [
    ("@we're not looking for 100% coverage", 2604, 2604, "we're not looking for 100% coverage, trading is an art, so some variations that are close to a set of rules applied based on context is what I hope we get out of it, then the challenge is to recreate those rules for apollo", None),
    ("@we're not looking for 100% coverage", 2606, 2606, "a small set of rules, each applied in a CONTEXT", None),
    ("@we're not looking for 100% coverage", 2606, 2606, "matched closely rather than exactly", None),
    ("@we're not looking for 100% coverage", 2606, 2606, "how much closer to his trades that gets than one rule for all; then those context rules are rebuilt for Apollo", None),
    ("@trail rest at break of 10 or 20d", 2046, 2047, "trail rest at break of 10 or 20d, I recall he mentioned 10d for faster stocks and 20d for slower stocks, also depend how far the are from 10/20", None),
    ("@trailed with the 10- or the 20-day moving average. Depends", 2095, 2096, "trailed with the 10- or the 20-day moving average. Depends on how fast the stock is", None),
    ("@what makes a stock 'faster'", 2054, 2055, "what makes a stock \"faster\" (e.g. its ADR), and how \"how far they are from the 10/20\" picks the average",
     "what makes a stock 'faster' (e.g. its ADR), and how 'how far they are from the 10/20' picks the average"),
    ("@paraphrased with short quotes", 1699, 1700, "Paraphrased with short quotes", "paraphrased with short quotes"),
    ("@if opening volume is large enough, buy a move above", 1712, 1713, "if opening volume is large enough, buy a move above the high of the FIRST 5-MINUTE bar; otherwise wait and buy above the first 1-HOUR bar", None),
    ("@the first 1-hour bar when volume needs confirming", 1735, 1736, "the first 1-hour bar when volume needs confirming", None),
    ("@his article l.1941-1942", 1941, 1942, "The opening range highs can be the highs of the first 1-minute candle, the 5-minute candle or the 60-minute candle.", None),
    ("@just look at the daily chart and enter when the stock is starting to break out", 2091, 2092, "just look at the daily chart and enter when the stock is starting to break out", None),
    ("@Stop is always lows of the day", 1943, 1943, "Stop is always lows of the day and stop should not be wider than the ATR or ADR of the stock.", None),
    ("@Better phrasing should be uptrend", 2481, 2481, "Better phrasing should be uptrend vs downtrend instead of bull/bear, under 200d but trending up can still be uptrend", None),
    ("@In a bullish market it is very common", 1948, 1948, "In a bullish market it is very common to get moves that are 10-20x+ your initial risk", None),
    ("@Hold for weeks or months", 1714, 1714, "Hold for weeks or months", None),
    ("@Stop: the low of the day", 1713, 1713, "Stop: the low of the day", None),
    ("@hold three to five days", 1732, 1732, "hold three to five days", None),
    ("@10d for faster stocks and 20d for slower stocks", 2046, 2047, "10d for faster stocks and 20d for slower stocks", None),
    ("@whose first candle is 09:30-10:00, l.2090", 2090, 2090, "the first candle is always only 30 minutes, 9.30-10 AM", "skip"),
]
for at, a, b, s_n, s_d in Q:
    in_notes = plain(s_n) in notes_span(a, b)
    in_doc = True if s_d == "skip" else plain(s_n if s_d is None else s_d) in DOCN
    res = "present" if (in_notes and in_doc) else ("ABSENT in notes lines" if not in_notes else "ABSENT in the doc (quote differs)")
    claim(at, f"notes l.{a}{'-' + str(b) if b != a else ''} holds, and the doc quotes verbatim: {s_n[:64]}{'…' if len(s_n) > 64 else ''}", "present", res,
          note="the doc paraphrases here (no verbatim check on the doc side)" if s_d == "skip" else "")
heading = [ln for ln in NOTES[:2481] if ln.startswith("## ")][-1]
claim("@Better phrasing", "notes: the l.2481 ruling sits under a heading dated 2026-10-22 (the doc: 'his 10-22 ruling')", "2026-10-22", heading[3:13], tok=False)
claim("@His rule for a miss (2026-10-23)", "notes: the 'defect in OUR implementation' rule is dated 2026-10-23", "2026-10-23",
      re.search(r"\((2026-10-2\d)\): for breakouts", NOTES[2561]).group(1))
claim("@his article l.1941-1942", "notes: the section holding l.1941-1942 says its quotes are the article's words", "article", "article" if "Quotes are the article's words" in " ".join(NOTES[1927:1941]) else "other")
claim("@the momentum burst", "notes: l.1727-1732 is the Momentum burst bullet block", "Momentum burst", "Momentum burst" if "Momentum burst" in " ".join(NOTES[1726:1732]) else "other")
q_line = next(i for i, ln in enumerate(NOTES, 1) if "looking for 100% coverage" in ln)
m_line = max(i for i, ln in enumerate(NOTES, 1) if ln.startswith("Method from this (#705): the target is not full coverage"))
claim("@l.2604", "notes: the quoted words are at l.2604 and the Method line at l.2606 (found by search)", "2604 / 2606", f"{q_line} / {m_line}", tok=False)
claim("@scripts/probes/_702_race_1022/03_market_trend_split.py", "03_market_trend_split.py l.1-3: SPY 50-day vs 10 sessions earlier; era-A data file is cb702_pre/ (not cb702_pre_v2/)", "present",
      "present" if ("50-day average higher than 10 sessions earlier" in " ".join(open(F_TREND).read().splitlines()[:3]).replace("\n", " ") and "cb702_pre/daily_closes_all" in open(F_TREND).read()) else "ABSENT")

# ===================================================================== 6. pins, files, repo references
say("\n## 6. §10 / §11: pins, files, data gate, repo references")
sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
claim("@sha256 `75c832541cef…`", "frozen rule-mix module sha256 prefix", "75c832541cef", sha(F_MIXMOD)[:12])
claim("@ac598fc58aae…", "frozen intraday module sha256 prefix", "ac598fc58aae", sha(F_INTMOD)[:12])
pins = open(F_MIXPINS).read()
claim("@`doc_body` (`6a2512024c5f…`)", "rule-mix pins: doc_body prefix", "6a2512024c5f", re.search(r"^- doc_body: (\w+)", pins, re.M).group(1)[:12])
bodies = sorted(os.listdir(D_BODIES))
hit = [b for b in bodies if sha(os.path.join(D_BODIES, b)).startswith("6a2512024c5f")]
claim("@`doc_body` (`6a2512024c5f…`)", "rule-mix freeze_bodies holds a body whose sha256 starts 6a2512024c5f", "yes", "yes" if hit else "no", note=str(hit))
fl = [ln for ln in open(LIST_FULL).read().splitlines() if ln]
claim("@19,470 pairs", "fetch list rows (pairs)", 19470, len(fl))
claim("@export_A", "export_A / export_B files exist", "yes / yes",
      f"{'yes' if os.path.exists(DATA + '/cb702_pre_v2/daily_closes_all.csv.gz') else 'no'} / {'yes' if os.path.exists(DATA + '/cb702/daily_closes_all.csv.gz') else 'no'}")
rp = open(F_REPLAY).read()
claim("@load_daily_subset", "01_replay.py: `def load_daily_subset` and `spy = tid[\"SPY\"]` (the calendar is built from SPY's rows)", "present",
      "present" if ("def load_daily_subset" in rp and 'spy = tid["SPY"]' in rp and "cal_days = days[start[spy]:stop[spy]]" in rp) else "ABSENT")
mixdoc = open(F_MIXDOC).read()
gpar = mixdoc[mixdoc.index("Guards (the intraday twelve"):mixdoc.index("Tests (synthetic")]
gnums = sorted({int(x) for x in re.findall(r"\((\d{1,2})\) ", gpar)})
claim("@Guards (the rule-mix's twelve", "rule-mix §9 guard paragraph: numbered guards", "12 (1..12)", f"{len(gnums)} ({gnums[0]}..{gnums[-1]})", tok=False)
claim("@R15", "frozen rule-mix module R15 = 'window controls in two modes, chance line the LARGER'", "present", "present" if re.search(r"R15 The window controls run in two modes", mod) else "ABSENT")
claim("--", "frozen rule-mix module R17 / R9 / R12 exist (R9 / R12 / R17 are cited by the module only)", "present", "present" if all(f"R{n} " in mod for n in (9, 12, 17)) else "ABSENT")
claim("@BALLPARK = within 0.25 ADR20", "reverse registration §6c: BALLPARK = within 0.25 ADR20 of the nearer edge", "0.25 ADR20", "0.25 ADR20" if re.search(r"6c\. BALLPARK.*\n.*\n0\.25 ADR20", open(F_REVDOC).read()) else "ABSENT")
claim("@the intraday §5b", "intraday registration §5b exists and names HIT / BALLPARK", "present", "present" if "5b. Feasibility, HIT, BALLPARK" in open(F_INTDOC).read() else "ABSENT")
claim("@FSLY 693: half on the 60-minute close 07-10", "rule-mix doc: 'one to two sessions before the last share left on 07-13 / 07-14'", "present", "present" if "one to two sessions before the last share left on 07-13 / 07-14" in " ".join(mixdoc.split()) else "ABSENT")
f693 = TX[TX.eid == "693"].iloc[0]
claim("@FSLY 693: half on the 60-minute close 07-10", "tags_exit eid 693 (FSLY): E / exit_lo_j / exit_hi_j", "2020-06-29 / 9 / 10", f"{f693.E} / {f693.exit_lo_j.replace('.0', '')} / {f693.exit_hi_j.replace('.0', '')}", tok=False)
sess = [ln.strip() for ln in open(f"{DATA}/cb702_pre_v2/sessions.txt") if ln.strip()]
si = {d: i for i, d in enumerate(sess)}
claim("@FSLY 693: half on the 60-minute close 07-10", "sessions from 07-10 to 07-13 / 07-14 on the era-A calendar", "1 / 2", f"{si['2020-07-13'] - si['2020-07-10']} / {si['2020-07-14'] - si['2020-07-10']}")
lo_j, hi_j = int(float(f693.exit_lo_j)), int(float(f693.exit_hi_j))
d10 = si["2020-07-10"] - si[f693.E]
claim("@two-session lag (FSLY's last share left", "§4a: 'FSLY's last share left two sessions after M-1's half' and ±1 'does not absorb' it - offsets: the half (07-10) vs the registered window [exit_lo_j, exit_hi_j]",
      "two sessions; not absorbed at ±1", f"07-10 = +{d10}; window [+{lo_j}, +{hi_j}]; half is {lo_j - d10} session before exit_lo_j and {hi_j - d10} before exit_hi_j; ±1 reaches exit_lo_j − 1 = +{lo_j - 1}",
      kind="MISMATCH" if d10 >= lo_j - 1 else "OK",
      note="the tolerance is measured against the WINDOW's edges (§4a: booked on exit_lo − 1 reads CLOSE), so a half on 07-10 sits inside ±1 of the 07-13..07-14 window; 'two sessions' holds only to the window's END (07-14). The rule-mix doc says 'one to two sessions'")
claim("@FSLY's two-session lag", "§12 repeats 'FSLY's two-session lag' as the case ±1 misses", "two-session lag, a miss beyond ±1", f"one session to exit_lo_j, two to exit_hi_j (as above)", kind="MISMATCH" if d10 >= lo_j - 1 else "OK",
      note="same finding as §4a; one fix covers both lines")
mix4b = mixdoc[mixdoc.index("**4b. The greedy tag**"):mixdoc.index("**4c. The composition line")]
mix4d = mixdoc[mixdoc.index("**4d. The R unit and the fill."):mixdoc.index("## 5. THE CONTROLS")]
has_q5 = bool(re.search(r"\n5\. \*\*.Losing. defined", mixdoc))
claim("@(its §4b / §11 Q5)", "§2 bullet: 'Losing' reused 'as it stands' (its §4b / §11 Q5) - where the rule-mix doc defines 'losing'", "§4b / §11 Q5",
      f"§11 Q5: {'yes' if has_q5 else 'no'}; §4d ('the losing test'): {'yes' if 'losing' in mix4d else 'no'}; §4b mentions losing: {'yes' if 'losing' in mix4b else 'no'}", kind="NOTE",
      note="§4b is the scorable denominator and greedy tag; the 'losing' test is defined at §4d and decided at §11 Q5. A cite slip, not a count")
cb = open(os.path.join(REPO, "agents/market_intelligence/consolidation_breakout.py")).read()
bg = open(os.path.join(REPO, "agents/market_intelligence/book_geometry_arms.py")).read()
yml = open(os.path.join(REPO, "data_gated_reviews.yaml")).read()
mbv = bool(re.search(r"^    v: np.ndarray", cb[cb.index("class MinuteBars"):cb.index("class MinuteBars") + 600], re.M))
dbv = bool(re.search(r"^    v: np.ndarray", cb[cb.index("class DailyBars"):cb.index("class DailyBars") + 600], re.M))
claim("@`MinuteBars.v`", "§10: `MinuteBars.v` and the loaded daily bars carry volume (consolidation_breakout.py dataclasses)", "both", f"MinuteBars.v {'yes' if mbv else 'no'}; DailyBars.v {'yes' if dbv else 'no'}", kind="OK" if (mbv and dbv) else "MISMATCH")
claim("@`ARMS`", "agents/market_intelligence/consolidation_breakout.py defines `ARMS` / `consolidation_breakout_pp.py` exists", "present / present",
      f"{'present' if re.search(r'^ARMS = ', cb, re.M) else 'ABSENT'} / {'present' if os.path.exists(os.path.join(REPO, 'agents/market_intelligence/consolidation_breakout_pp.py')) else 'ABSENT'}")
claim("@`_HOUR_ENTRY_ARMS`", "book_geometry_arms.py defines `_HOUR_ENTRY_ARMS`", "present", "present" if re.search(r"^_HOUR_ENTRY_ARMS = ", bg, re.M) else "ABSENT")
m_ = re.search(r"review_id: consolidation_breakout_forward_read.*?threshold: (\d+)", yml, re.S)
claim("@30 settled C1 entries", "data_gated_reviews.yaml: consolidation_breakout_forward_read threshold", 30, int(m_.group(1)))

# ===================================================================== 7. G1 column names; the bucket vs booked_j premise of G3
say("\n## 7. §11 G1 / G3: the tag files' columns and the (bucket, booked_j) premise of the ±k mapping")
for nm, t, need in (("tags_stop", TS, ["S1-T_bucket", "S1-T_first_j", "S1-T_booked_j", "tag", "earliest_tag", "ctl_a_union", "ctl_b_union", "rlevel_ex"]),
                    ("tags_exit", TX, ["M-1_bucket", "M-1_first_j", "M-1_booked_j", "tag", "earliest_tag", "ctl_a_union", "ctl_b_union", "rlevel_ex"]),
                    ("tags_enter", TE, ["L1_bucket", "tag", "earliest_tag", "kprice_union", "shared_union"])):
    claim("@G1 identity", f"{nm}: columns the G1 sentence names exist", "all present", "all present" if all(c in t.columns for c in need) else f"missing {[c for c in need if c not in t.columns]}")
claim("@G1 identity", "tags_enter carries `first_j` / `booked_j` (G1 lists '(bucket, first_j, booked_j, tag, earliest_tag)' for `tags_{enter,stop,exit}.tsv`)", "present in all three",
      "present" if any(c.endswith("_first_j") for c in TE.columns) else "ENTER has `<rule>_cross` and `<rule>_bucket`, no first_j / booked_j", kind="NOTE",
      note="STOP / EXIT have bucket, first_j, booked_j, first_minute; ENTER has bucket and cross")
claim("@the files carry no missing-session or buy-day-frame flags", "tag files' columns containing 'flag' / 'frame' / 'missing' / 'no_bar'", "none",
      str([c for t in (TE, TS, TX) for c in t.columns if re.search(r"flag|frame|missing|no_bar", c)] or "none"))
prem = collections.Counter()
for nm, df, rules in (("STOP", STP, RUL["STOP"]), ("EXIT", EXT, RUL["EXIT"])):
    lo, hi = df.exit_lo_j.astype(float).values, df.exit_hi_j.astype(float).values
    for r in rules:
        b = df[r + "_bucket"].values
        bk = pd.to_numeric(df[r + "_booked_j"], errors="coerce").values
        for i in range(len(df)):
            if np.isnan(bk[i]):
                prem[(b[i], "no firing")] += 1
            else:
                prem[(b[i], "before" if bk[i] < lo[i] else ("in" if bk[i] <= hi[i] else "after"))] += 1
ok_ex = prem[("EXPLAINS", "before")] + prem[("EXPLAINS", "after")] + prem[("EXPLAINS", "no firing")]
ok_me = prem[("MISS-EARLY", "in")] + prem[("MISS-EARLY", "after")] + prem[("MISS-EARLY", "no firing")]
ok_ne = prem[("NEITHER", "before")] + prem[("NEITHER", "in")]
claim("@G3 tolerance consistency", "G3 premise on the tag files: EXPLAINS booked outside the window / MISS-EARLY booked not before it / NEITHER booked before or inside it (cells of STOP + EXIT, all blocks)", "0 / 0 / 0",
      f"{ok_ex} / {ok_me} / {ok_ne}", note=f"UNRESOLVED booked: {prem[('UNRESOLVED', 'before')]} before, {prem[('UNRESOLVED', 'in')]} inside (the buy-day-frame / missing-session cases)")

# ===================================================================== 8. buy-day minute coverage (fetch logs only)
say("\n## 8. §10: the minute fetch holds every buy day (fetch logs / lists only; NO bar file opened)")


def load_done(tree):
    out = {}
    with open(tree + "/_done.psv") as fh:
        for ln in fh:
            f = ln.rstrip("\n").split("|")
            if len(f) < 4 or f[0] > CUT:
                continue
            out[(f[0], f[1])] = f[3]
    return out


DONE = {k: load_done(TREES[k]) for k in TREE_ORDER}
DFILES = {k: {fn[:-len(".psv.gz")] for fn in os.listdir(TREES[k]) if fn.endswith(".psv.gz")} for k in TREE_ORDER}
INT_DONE = load_done(INTRA_MIN)
sym_a = dict(zip(E.eid, E.sym_a))


def state(d, tk):
    for k in TREE_ORDER:
        if DONE[k].get((d, tk)) == "ok" and d in DFILES[k]:
            return "ok"
    if INT_DONE.get((d, tk)) == "ok":
        return "ok"
    for k in TREE_ORDER:
        if DONE[k].get((d, tk)) == "empty":
            return "empty"
    if INT_DONE.get((d, tk)) == "empty":
        return "empty"
    return "missing"


for dec in ("ENTER", "STOP", "EXIT"):
    for b in BLK:
        x = SETS[dec][SETS[dec].block == b]
        st = collections.Counter(state(r.E, sym_a[r.eid] if r.E <= A_LAST else r.sym) for r in x.itertuples())
        claim("@buy day (C-E1's five minutes", f"{dec} {b}: scorable buy days with a minute file / empty at source / absent from every tree and the fetch", "all present (absent 0)",
              f"ok {st['ok']} / empty {st['empty']} / absent {st['missing']}", kind="OK" if st["missing"] == 0 else "MISMATCH",
              note="empty at source -> C-E1 MISSING (§3d), counted" if st["empty"] else "")

# ===================================================================== 9. self-consistency of the doc's own cross-references
say("\n## 9. The doc's own cross-references (a section / gate / guard named in the text exists in the text)")
full = "\n".join(DL)
for ref, pat in (("§5c", r"\*\*5c\."), ("§5e", r"\*\*5e\."), ("§6b", r"\(b\) SHUF"), ("§6c-1", r"\(c-1\)"), ("§7c", r"\*\*7c\."), ("§3d", r"\*\*3d\."), ("§4b", r"\*\*4b\."), ("§1 4h", r"\(h\) \*\*The bracket"),
                 ("§11 G1", r"\*\*G1 identity\*\*"), ("§11 G2", r"\*\*G2\*\*"), ("§11 G3", r"\*\*G3 tolerance"), ("§11 G4", r"\*\*G4\*\*"), ("§11 G5", r"\*\*G5\*\*"), ("§11 G6", r"\*\*G6\*\*"),
                 ("guard D1", r"\*\*Added: \(D1\)\*\*"), ("guard D2", r"\*\*\(D2\)\*\*"), ("guard D3", r"\*\*\(D3\)\*\*"), ("guard D4", r"\*\*\(D4\)\*\*"),
                 ("§13 Q1", r"\n1\. \*\*ENTER's"), ("§13 Q2", r"\n2\. \*\*EXIT contexts"), ("§13 Q3", r"\n3\. \*\*The full library"), ("§13 Q4", r"\n4\. \*\*The 10/20 switch")):
    claim("--", f"cross-reference target exists: {ref}", "present", "present" if re.search(pat, full) else "ABSENT")
claim("@Four design forks", "§0 says 'Four design forks'; §13 has Q1..Q4", 4, len(re.findall(r"\n[1-9]\. \*\*", full[full.index("## 13. Design questions"):full.index("## 14. Revisions")])), tok=False)
claim("@Code:", "the module folder named in §11 vs the folder this recount lives in", "scripts/probes/_705_context_rules_1026/", "scripts/probes/_705_context_1026/", kind="MISMATCH",
      note="§11 'Code' (and the §11 Outputs 'in the module's folder') name _705_context_rules_1026; the probes folder in use is _705_context_1026. Pick one before the freeze - the pins, ledger, dry-run path and the module scan key on the folder")

# ================================================================================================== summary
say("\n## Summary")
bad = [c for c in CLAIMS if c[4] == "MISMATCH"]
notes = [c for c in CLAIMS if c[4] == "NOTE"]
say(f"- claims: {len(CLAIMS)}; OK {sum(1 for c in CLAIMS if c[4] == 'OK')}; MISMATCH {len(bad)}; NOTE {len(notes)}; unresolved doc anchors {len(UNRESOLVED)}")
if UNRESOLVED:
    say("- UNRESOLVED anchors (doc line shown as '?'): " + "; ".join(UNRESOLVED))
say("\n## DOC-TOKEN CHECK (every number in the 'doc' column must occur within the 4 lines before / 1 after its anchor in the registration; a failure here is MY transcription, not a doc finding)")
for ln_, lab_, d_, lost_ in DOC_TOKEN_WARN:
    say(f"[L{ln_}] {lab_} | doc column {d_} | tokens not found near the anchor: {lost_}")
if not DOC_TOKEN_WARN:
    say("(none)")
say("\n## MISMATCH lines")
for c in bad:
    say(f"[L{c[0]}] {c[1]} | doc {fmt(c[2])} | mine {fmt(c[3])}" + (f" | {c[5]}" if c[5] else ""))
if not bad:
    say("(none)")
say("\n## NOTE lines")
for c in notes:
    say(f"[L{c[0]}] {c[1]} | doc {fmt(c[2])} | mine {fmt(c[3])}" + (f" | {c[5]}" if c[5] else ""))
with open(OUT_TXT, "w", encoding="utf8") as fh:
    fh.write("\n".join(LINES) + "\n")
sys.exit(0)
