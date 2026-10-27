#!/usr/bin/env python3
"""#711 fork count (2026-10-27, before any R1 number): how many of the R1-input statements a HELD-POSITION join would place, from the
readers' labels and the windows' existence only. NO price is compared with any range, no control is built, nothing is scored."""
import collections, importlib.util, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); D = os.path.dirname(HERE)
sys.path.insert(0, os.path.abspath(os.path.join(D, "..", "..", "..")))
spec = importlib.util.spec_from_file_location("chk03", os.path.join(D, "03_check.py")); M = importlib.util.module_from_spec(spec)
sys.modules["chk03"] = M; spec.loader.exec_module(M)
K, P, CAP = M.K, M.P, M.CAP
quiet = lambda *a, **k: None
rows = K.read_sheets(); ranges = K.read_ranges(); tally = collections.Counter()
L = P.load_all(quiet, tally); P.preload_minutes(L, quiet)
engine = K.RangeEngine(L); S = L["S"]
w = K.windows_tuple(L["buys"] + L["sales"]); by_sym, holds = CAP.index_windows(w), CAP.index_holds(w)
st = M.build_statements(rows, by_sym, holds, ranges, engine, S)
r1 = [s for s in st if M.is_r1_input(s)]
def has_range(eid, side):
    r = ranges.get((int(eid), side)) if eid not in ("", None) else None
    return bool(r) and K.raw_range(r) is not None
def side_for(s):
    if s["action"] == "holding" and s["price_kind"] == "entry":
        return "buy"
    return {"buy": "buy", "sell": "sale"}.get(s["side_of_action"], "")
cur = [s for s in r1 if M.is_primary(s)]
amend = {"held_mid_hold": 0, "held_tie_one_position": 0}
amend_any_day = {"held_mid_hold": 0, "held_tie_one_position": 0}
for s in r1:
    cls = "held_mid_hold" if (s["join_status"] == "none" and s["join_reason"] == "inside_hold" and s["beside_eid"]) else \
          ("held_tie_one_position" if (s["join_status"] == "ambiguous" and s["beside_eid"]) else None)
    if not cls:
        continue
    sd = side_for(s)
    clean_fill = s["fill"] == "fill" and not s["garbled"] and (s["matched"] or (s["action"] == "holding" and s["price_kind"] == "entry"))
    if sd and clean_fill and has_range(s["beside_eid"], sd):
        amend_any_day[cls] += 1
        if s["day_named"]:
            amend[cls] += 1
by = collections.Counter((s["join_status"], s["join_reason"]) for s in r1)
print(f"R1 input {len(r1)}; join classes {dict(by)}")
print(f"PRIMARY as registered: {len(cur)}")
print(f"held-position join adds (clean fill, matched or holding/entry, side's window has a range): named day {amend}, any day class {amend_any_day}")
print(f"=> primary under the amendment: named-day {len(cur) + sum(amend.values())}; any day class for held statements {len(cur) + sum(amend_any_day.values())}")
