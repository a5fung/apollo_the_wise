#!/usr/bin/env python3
"""#705 as-is read, STEP 6b: the reconstruction checked against his own words (docs/analysis/cb_asis_reconstruction_prereg_2026-10-26.md §4.1
step 6-7, §4.2). RULE-FREE BY CONSTRUCTION: the join reads the readers' ticker and the stream date only (never the action, never the price);
the pinned step-5 / 6a modules are loaded read-only through asis_check_common (nothing is imported from the four rule folders).

WHAT IT DOES
  input     the readers' v2 price batch (reader1_t1_v2_part1-3.tsv under sheets_filled/): his own trade + ticker identified + price stated =
            the R1 input (102 per the freeze record); every own-trade, ticker-identified row (194) for R3 and R5 (asis_check_common R70).
  join      §4.1 step 6: symbol (the READERS' ticker, never the machine's hit symbol) + the stream date (R62) -> the nearest window of EITHER
            side whose span contains the day or lies within one session of it (02_captions.join_position); a tie is `ambiguous` (R69), no
            window within a session is `none` with its reason. Counts printed: joined / ambiguous / no window.
  R1        §4.2: the share of stated FILL prices (R63; clean only, R64) inside the trade's reachable range read from ranges.tsv's RAW
            columns with the §4.2 tolerance (R68); the bars-only range primary, with the panel price beside. The PRIMARY count is chosen by
            the reader's labels alone (R85): the price kind matches the action's side and the day class names a day; holding/entry,
            side-mismatched and unstated/approx-day fills are scored BESIDE. Controls: (a) the same stock's window shifted -3..+3 sessions,
            re-ranged by 01_points' own functions (R66); (b) another name he held that day under the same join rule (R67). Bar: real minus
            EACH control >= 25 points; the §9 floor on the SCORED n (R65) — under 100 primary statements the bar is NOT DECIDABLE and the
            would-be verdict is carried beside. Printed by bracket type with `pre_market_possible` on its own line, the garbled line
            beside, and every split (2020 / 2021-22, with / without flickers, with / without daily-only sources); only the primary line
            carries a verdict, every other row says 'beside (no bar)' (§4.2).
  R3        the day-offset histogram (stated day - window start / end, in sessions) by the reader's day class; the inside share secondary;
            beside it the `other_date` statements' distance to the nearest window of their name (R88, secondary).
  R4        the implied move (dollar result / shares, % of the entry price) against the trade's band of outcomes (R71).
  R5        side agreement after the join (R72), bar >= 90%.
  labels    the consequence table's sentences printed exactly as §4.2 words them (asis_check_common.CONSEQUENCE_LABELS).
  anchors   per (position, side): the mean primary fill price (R73) -> check_r1_r5.tsv with `stated_outside_range` per statement and
            `side_outside_range` per side (R74, R86; ranges.tsv is never written).

STAGES  --dry-run    inputs, populations, the join's counts, the control populations, the §4.1 step-7 beside table, the claims against the
                     freeze record and the plan -> 03_check_dryrun.txt ending 'DRY RUN COMPLETE' with a RESULT line. NO containment, no
                     scorer is called (R81): no R1 number exists in a dry run.
        --print-pins the sha256 pins of every input, the modules, the doc body and this stage's dry-run printout -> 03_check_pins.txt.
        --run        REFUSES (03_check.refused.txt) unless the dry run completed with 0 MISMATCH by these modules, every pin incl. doc_body and
                     the dry-run printout sits below the doc's freeze marker, the ledger verifies and no output exists (run_gate '6b');
                     otherwise writes check_r1_r5.tsv, control_ranges.tsv and 03_check.txt, and appends the step6b_* ledger rows.

        --archive    (re-run 2, asis_check_common R90) moves 6b's first-run files to *_run1 with `archive_run1_6b_*` ledger rows.
  re-run 2 (2026-10-27): the windows are v2 (01_points R44); the population claims read ranges.tsv against the LOADED windows with §3.1's
                    figures beside (R89); a dry run before step 5's re-run 2 STOPS on the absent ranges.tsv (R90); the bars are unchanged.

Run:  python3 scripts/probes/_705_asis_1026/03_check.py --archive | --dry-run | --print-pins | --run
No subagent, no network, no production server, no paid call, nothing after 2024-12-31, none of the seven outcome folders.
"""
from __future__ import annotations

import argparse
import collections
import importlib.util
import os
import statistics
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))


def _load_check_common():
    name, path = "asis_check_common", os.path.join(HERE, "asis_check_common.py")
    if name in sys.modules and getattr(sys.modules[name], "__file__", "") == path:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


K = _load_check_common()
C, P, CAP = K.C, K.P, K.CAP
Say, Claims, table, pct, fmt = K.Say, K.Claims, K.table, K.pct, K.fmt

SCAN_FILES = ("asis_common.py", "01_points.py", "02_captions.py", "asis_check_common.py", "03_check.py")
CHECK_COLS = ["stmt_id", "sid", "part", "stream_date", "ticker", "action", "side_of_action", "side_said", "day_class", "price_kind", "fill",
              "matched", "day_named", "primary", "price_raw", "garbled", "shares", "dollar_result", "join_status", "join_reason", "eid",
              "side", "dist", "tied", "bracket", "flicker", "resolution", "year", "in_span", "pre_market_possible", "range_lo_raw",
              "range_hi_raw", "raw_factor", "session_range_raw", "tolerance", "inside", "inside_with_panel", "shifted_inside",
              "shifted_share", "cross_n", "cross_share", "r5_agree", "offset_start", "offset_end", "nearest_offset", "beside_eid",
              "beside_buy", "beside_sale", "anchor_price_raw", "anchor_price_bar", "stated_outside_range", "side_outside_range", "flags"]
CONTROL_COLS = ["stmt_id", "control", "k", "symbol", "eid", "side", "lo", "hi", "bracket", "resolution", "range_lo_raw", "range_hi_raw",
                "session_range_raw", "tolerance", "inside"]
BRACKET_WORDS = P.BRACKET_WORDS


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the statements, joined
# ═════════════════════════════════════════════════════════════════════════════════════════════
def build_statements(rows: list, by_sym: dict, holds: dict, ranges: dict, engine, S) -> list:
    """Every own-trade, ticker-identified row joined by symbol and day; the joined window's ranges.tsv facts attached. No score."""
    out = []
    for r, k in K.own_identified(rows):
        day = K.statement_day(r)
        j = K.join(k["ticker"], day, by_sym, S)
        rec = {"stmt_id": r["stmt_id"], "sid": r.get("sid", ""), "part": r["part"], "stream_date": day, "ticker": k["ticker"], "action": k["action"],
               "side_of_action": k["side_of_action"], "side_said": k["side_said"], "day_class": k["day_class"], "price_kind": k["price_kind"],
               "fill": k["fill"], "matched": k["matched"], "day_named": k["day_named"], "primary": "",
               "price_raw": "" if k["price"] is None else k["price"], "garbled": k["garbled"], "priced": k["priced"],
               "shares": "" if k["shares"] is None else k["shares"], "dollar_result": "" if k["dollar_result"] is None else k["dollar_result"],
               "join_status": j["status"], "join_reason": CAP.none_reason(k["ticker"], day, by_sym, holds, S) if j["status"] == "none" else "",
               "eid": j["eid"], "side": j["side"], "dist": j["dist"], "tied": j.get("tied", ""), "window": None, "row": None, "beside_eid": "",
               "nearest_offset": ""}
        if j["status"] == "none" and rec["join_reason"] == "other_date":          # R88: how far the nearest window of the name sits (beside R3)
            off = K.nearest_window_offset(k["ticker"], day, by_sym, S)
            rec["nearest_offset"] = "" if off is None else off
        if j["status"] == "none" and rec["join_reason"] == "inside_hold":          # R82: the hold the day sits in (a readout beside, never the bar)
            di = S.le(day)
            rec["beside_eid"] = next((str(e) for e, end, start in holds.get(k["ticker"], ()) if S.le(end) < di < S.ge(start)), "")
        elif j["status"] == "ambiguous" and CAP.tie_is_one_position(j):            # R83: one position's two windows on a day-trade day
            rec["beside_eid"] = j["tied"].split(":")[0]
        if j["status"] == "unique":
            rec["window"] = engine.window(j["eid"], j["side"])
            rec["row"] = ranges.get((int(j["eid"]), j["side"]))
            row = rec["row"] or {}
            rec.update({"bracket": row.get("bracket", ""), "flicker": row.get("flicker", ""), "resolution": row.get("resolution", ""),
                        "year": row.get("year", ""), "in_span": row.get("in_span", ""),
                        "pre_market_possible": "pre_market_possible" in (row.get("flags") or ""), "flags": row.get("flags", ""),
                        "raw_factor": row.get("raw_factor", "")})
            rr = K.raw_range(row)
            rec["range_lo_raw"], rec["range_hi_raw"] = ("", "") if rr is None else rr
            rec["offset_start"], rec["offset_end"] = K.day_offsets(day, row["lo"], row["hi"], S) if row else ("", "")
        out.append(rec)
    return out


def join_counts(stmts: list) -> dict:
    c = collections.Counter(s["join_status"] for s in stmts)
    reasons = collections.Counter(s["join_reason"] for s in stmts if s["join_status"] == "none")
    one_pos = sum(1 for s in stmts if s["join_status"] == "ambiguous" and CAP.tie_is_one_position({"status": "ambiguous", "tied": s["tied"]}))
    return {"n": len(stmts), "unique": c["unique"], "ambiguous": c["ambiguous"], "ambiguous_one_position": one_pos, "none": c["none"],
            "none_reasons": dict(reasons)}


def is_r1_input(s: dict) -> bool:
    return s["priced"] and s["price_raw"] != ""


def is_scorable(s: dict) -> bool:
    """A priced statement uniquely joined to a window that has a range: the only statements any R1 line can score."""
    return is_r1_input(s) and s["join_status"] == "unique" and s["range_lo_raw"] != ""


def is_clean_fill(s: dict) -> bool:
    return is_scorable(s) and s["fill"] == "fill" and not s["garbled"]


def is_primary(s: dict) -> bool:
    """R1's primary count (R85): a clean FILL whose price kind matches the action's side, on a day class that names a day, uniquely joined
    to a window with a range. Chosen by the reader's labels, never by where the statement landed."""
    return is_clean_fill(s) and s["matched"] and s["day_named"]


def is_unmatched_fill(s: dict) -> bool:
    """Beside (R85): a clean fill whose price is not the kind of its action's side — holding/entry (a past fill), an entry price on a sale
    action, an exit price on a buy action."""
    return is_clean_fill(s) and not s["matched"]


def is_unnamed_day_fill(s: dict) -> bool:
    """Beside (R85): a clean, matched fill whose day class does not name a day (unstated / approx_earlier)."""
    return is_clean_fill(s) and s["matched"] and not s["day_named"]


def is_garbled_line(s: dict) -> bool:
    return is_scorable(s) and s["fill"] == "fill" and s["garbled"]


def is_level_line(s: dict) -> bool:
    return is_scorable(s) and s["fill"] == "level"


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the controls' populations (built in the dry run, scored only in --run)
# ═════════════════════════════════════════════════════════════════════════════════════════════
def build_controls(stmts: list, by_sym: dict, ranges: dict, engine, S, say) -> list:
    """For every priced, uniquely joined statement with a range: the six shifted windows' rows (R66) and the cross names' rows (R67).
    -> control rows (no `inside` yet). The shifted pairs are preloaded in one pass first (one file read per tree and date)."""
    targets = [s for s in stmts if is_r1_input(s) and s["join_status"] == "unique" and s["range_lo_raw"] != ""]
    t0 = time.time()
    shifted = {}
    pairs = set()
    for s in targets:
        for k in K.SHIFTS:
            w2 = K.shifted_window(s["window"], k, S)
            if w2 is None:
                continue
            P.reachable(w2, S)
            P.assign_export(w2, engine.bars, engine.tally)
            shifted[(s["stmt_id"], k)] = w2
            if not w2.wide:
                pairs |= {(d, w2.bar_sym) for d, _, _ in w2.reach}
    st = engine.bars.store.preload(sorted(pairs))
    say(f"- control (a): {len(shifted):,} shifted windows for {len(targets):,} statements; {len(pairs):,} (session, symbol) pairs preloaded -> "
        + ", ".join(f"{k} {v:,}" for k, v in sorted(st.items())) + f" ({time.time() - t0:.0f}s)")
    rows = []
    for s in targets:
        for k in K.SHIFTS:
            w2 = shifted.get((s["stmt_id"], k))
            if w2 is None:
                rows.append({"stmt_id": s["stmt_id"], "control": "shifted", "k": k, "symbol": s["ticker"], "eid": s["eid"], "side": s["side"],
                             "lo": "", "hi": "", "bracket": "", "resolution": "none", "range_lo_raw": "", "range_hi_raw": "", "session_range_raw": "",
                             "tolerance": "", "inside": "", "_w": None})
                continue
            rng = engine.range_row(w2)
            rr = K.raw_range(rng)
            day_k = S.date(S.le(s["stream_date"]) + k) if 0 <= S.le(s["stream_date"]) + k < len(S.cal) else w2.lo
            sr = engine.session_range_raw(w2, day_k) if rr is not None else None
            rows.append({"stmt_id": s["stmt_id"], "control": "shifted", "k": k, "symbol": s["ticker"], "eid": s["eid"], "side": s["side"],
                         "lo": w2.lo, "hi": w2.hi, "bracket": w2.bracket, "resolution": rng["resolution"],
                         "range_lo_raw": "" if rr is None else rr[0], "range_hi_raw": "" if rr is None else rr[1],
                         "session_range_raw": "" if sr is None else round(sr, 4), "tolerance": "", "inside": "", "_w": w2})
        for sym, eid2, side2 in K.cross_names(s["ticker"], s["stream_date"], by_sym, S):
            w3 = engine.window(eid2, side2)
            row3 = ranges.get((int(eid2), side2)) or {}
            rr = K.raw_range(row3)
            sr = engine.session_range_raw(w3, s["stream_date"]) if (rr is not None and w3 is not None) else None
            rows.append({"stmt_id": s["stmt_id"], "control": "cross", "k": "", "symbol": sym, "eid": eid2, "side": side2, "lo": row3.get("lo", ""),
                         "hi": row3.get("hi", ""), "bracket": row3.get("bracket", ""), "resolution": row3.get("resolution", "none"),
                         "range_lo_raw": "" if rr is None else rr[0], "range_hi_raw": "" if rr is None else rr[1],
                         "session_range_raw": "" if sr is None else round(sr, 4), "tolerance": "", "inside": "", "_w": w3})
    return rows


def control_populations(stmts: list, controls: list) -> dict:
    by = collections.defaultdict(lambda: {"shifted_ranged": 0, "shifted_total": 0, "cross_ranged": 0, "cross_total": 0})
    for c in controls:
        b = by[c["stmt_id"]]
        key = c["control"]
        b[f"{key}_total"] += 1
        b[f"{key}_ranged"] += c["range_lo_raw"] != ""
    targets = [s for s in stmts if s["stmt_id"] in by]
    return {"statements": len(targets),
            "with_any_shift": sum(1 for s in targets if by[s["stmt_id"]]["shifted_ranged"] > 0),
            "with_all_six": sum(1 for s in targets if by[s["stmt_id"]]["shifted_ranged"] == 6),
            "with_any_cross": sum(1 for s in targets if by[s["stmt_id"]]["cross_ranged"] > 0),
            "cross_names_median": statistics.median([by[s["stmt_id"]]["cross_ranged"] for s in targets]) if targets else 0,
            "by": by}


# ═════════════════════════════════════════════════════════════════════════════════════════════
# scoring (--run only, R81)
# ═════════════════════════════════════════════════════════════════════════════════════════════
def score(stmts: list, controls: list, ranges: dict, engine, S) -> None:
    """Fills `inside`, the control shares, R5 and the offsets on every statement; `inside` on every control row."""
    ctrl_by = collections.defaultdict(list)
    for c in controls:
        ctrl_by[c["stmt_id"]].append(c)
    for s in stmts:
        s.update({"inside": "", "inside_with_panel": "", "shifted_inside": "", "shifted_share": "", "cross_n": 0, "cross_share": "",
                  "session_range_raw": "", "tolerance": "", "r5_agree": "", "beside_buy": "", "beside_sale": ""})
        if s["beside_eid"] and is_r1_input(s):                                      # R82 / R83: against the position's two windows, beside
            price = float(s["price_raw"])
            for side in ("buy", "sale"):
                row, w = ranges.get((int(s["beside_eid"]), side)), engine.window(s["beside_eid"], side)
                rr = K.raw_range(row or {})
                if rr is not None and w is not None:
                    s[f"beside_{side}"] = K.contains(price, rr[0], rr[1], K.tolerance(price, engine.session_range_raw(w, s["stream_date"])))
        if s["join_status"] != "unique":
            continue
        if s["action"] in K.SIDE_OF_ACTION:
            s["r5_agree"] = K.SIDE_OF_ACTION[s["action"]] == s["side"]
        if not is_r1_input(s) or s["range_lo_raw"] == "":
            continue
        price = float(s["price_raw"])
        sr = engine.session_range_raw(s["window"], s["stream_date"])
        tol = K.tolerance(price, sr)
        s["session_range_raw"], s["tolerance"] = ("" if sr is None else round(sr, 4)), round(tol, 4)
        s["inside"] = K.contains(price, float(s["range_lo_raw"]), float(s["range_hi_raw"]), tol)
        row = s["row"]
        if row.get("range_lo_with_panel") not in ("", None) and row.get("raw_factor") not in ("", None):
            f = float(row["raw_factor"])
            s["inside_with_panel"] = K.contains(price, float(row["range_lo_with_panel"]) * f, float(row["range_hi_with_panel"]) * f, tol)
        sh, cr = [], []
        for c in ctrl_by.get(s["stmt_id"], ()):
            if c["range_lo_raw"] == "":
                continue
            ctol = K.tolerance(price, None if c["session_range_raw"] == "" else float(c["session_range_raw"]))
            c["tolerance"] = round(ctol, 4)
            c["inside"] = K.contains(price, float(c["range_lo_raw"]), float(c["range_hi_raw"]), ctol)
            (sh if c["control"] == "shifted" else cr).append(c["inside"])
        s["shifted_inside"] = "".join("1" if x else "0" for x in sh)
        s["shifted_share"] = "" if not sh else round(K.share(sh), 2)
        s["cross_n"], s["cross_share"] = len(cr), ("" if not cr else round(K.share(cr), 2))
        s["_shifted_flags"], s["_cross_flags"] = sh, cr


def r1_block(stmts: list, floor: int = K.T1_FLOOR) -> dict:
    """R1 on a set of scored statements: raw share, the two control shares, the gap bar with the §9 floor on THIS set's n (R65)."""
    real = K.share([s["inside"] for s in stmts])
    panel = K.share([s["inside_with_panel"] for s in stmts if s["inside_with_panel"] != ""])
    shifted = K.control_share([s.get("_shifted_flags", []) for s in stmts])
    cross = K.control_share([s.get("_cross_flags", []) for s in stmts])
    g = K.gap_bar(real, shifted, cross, len(stmts), floor)
    return {"n": len(stmts), "real": real, "with_panel": panel, "shifted": shifted, "cross": cross,
            "n_shifted": sum(1 for s in stmts if s.get("_shifted_flags")), "n_cross": sum(1 for s in stmts if s.get("_cross_flags")), **g}


def r1_row(label: str, b: dict, bar: bool = False) -> list:
    """A printout row; only the primary line (`bar`) carries a verdict, every other row says NO_BAR (§4.2 'no separate bar'; review F6)."""
    verdict = (b["verdict"] + (f" (would be {b['would_be']})" if b["verdict"] == K.VERDICT_ND and b["would_be"] else "")) if bar else K.NO_BAR
    return [label, b["n"], fmt(b["real"]), fmt(b["with_panel"]), f"{fmt(b['shifted'])} (n {b['n_shifted']})", f"{fmt(b['cross'])} (n {b['n_cross']})",
            fmt(b["gap_shifted"]), fmt(b["gap_cross"]), verdict]


R1_HDR = ["set", "n", "inside %", "with panel %", "shifted %", "cross %", "gap shifted", "gap cross", "verdict"]


def anchors(stmts: list) -> dict:
    """R73: {(eid, side): {price_raw, price_bar, n, spread, differ, outside}} from the PRIMARY statements (R85) uniquely joined; `outside` is
    the side's flag (any of its statements outside, R86)."""
    by = collections.defaultdict(list)
    for s in stmts:
        if is_primary(s):
            by[(int(s["eid"]), s["side"])].append(s)
    out = {}
    for key, ss in by.items():
        prices = [float(s["price_raw"]) for s in ss]
        mean = sum(prices) / len(prices)
        tol = max(float(s["tolerance"]) for s in ss) if all(s.get("tolerance") not in ("", None) for s in ss) else K.tolerance(mean, None)
        row = ss[0]["row"]
        f = float(row["raw_factor"]) if row.get("raw_factor") not in ("", None) else 1.0
        outside = any(s["inside"] is False for s in ss)
        out[key] = {"price_raw": round(mean, 4), "price_bar": round(mean / f, 4) if f else "", "n": len(ss), "spread": round(max(prices) - min(prices), 4),
                    "differ": (max(prices) - min(prices)) > tol, "outside": outside, "stmts": [s["stmt_id"] for s in ss]}
    return out


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the printouts
# ═════════════════════════════════════════════════════════════════════════════════════════════
def clock_text(m: float) -> str:
    """Minutes since 09:30 -> 'HH:MM' ET."""
    t = int(m) + 570
    return f"{t // 60:02d}:{t % 60:02d}"


def beside_table(say, stmts: list, ranges: dict, engine, S) -> None:
    """§4.1 step 7: the price-stated (joined) positions beside every in-span position: hold length, flicker share, bracket type, time of day."""
    priced_keys = {(int(s["eid"]), s["side"]) for s in stmts if is_r1_input(s) and s["join_status"] == "unique"}
    allrows = [r for r in ranges.values() if r["in_span"] == "True"]
    sets = (("price-stated, joined", [r for r in allrows if (int(r["eid"]), r["side"]) in priced_keys]), ("all in-span sides", allrows))
    say("\n## §4.1 step 7 — the price-stated trades beside the rest (before any anchor)")
    rows = []
    for name, rs in sets:
        for side in ("buy", "sale"):
            ss = [r for r in rs if r["side"] == side]
            holds = [float(x["hold_sessions_max"]) for r in ss for x in [ranges.get((int(r["eid"]), "sale"))] if x and x["hold_sessions_max"] not in ("", None)]
            clocks = []
            for r in ss:
                w = engine.window(r["eid"], side)
                f = (w.later if side == "buy" else w.earlier) if w is not None else None
                m = P.clock_minute(f.clock) if (f is not None and f.ctx == "in") else None
                if m is not None:
                    clocks.append(m)
            br = collections.Counter(r["bracket"] for r in ss)
            top = ", ".join(f"{b} {pct(n, len(ss))}" for b, n in br.most_common(3))
            rows.append([name, side, len(ss), fmt(statistics.median(holds), 0) if holds else "n/a", pct(sum(r["flicker"] == "True" for r in ss), len(ss)),
                         pct(sum(r["resolution"] == "daily_only" for r in ss), len(ss)),
                         clock_text(statistics.median(clocks)) if clocks else "n/a", top])
    table(say, ["set", "side", "n", "median hold (sessions, max, the position's)", "flicker", "daily-only", "median frame clock ET", "bracket types"], rows)


def report_populations(say, rows: list, stmts: list, ranges: dict, claims, windows: list = None) -> dict:
    say("\n## Populations")
    say(f"- v2 price batch: {len(rows):,} rows in {len(set(r['part'] for r in rows))} parts; " +
        ", ".join(f"{p} {n}" for p, n in sorted(collections.Counter(r['part'] for r in rows).items())))
    ks = [K.classify(r) for r in rows]
    own = [k for k in ks if k["own"]]
    say(f"- his own trade: {len(own):,}; ticker identified Y {sum(k['ident'] == 'Y' for k in own):,}, amb {sum(k['ident'] == 'amb' for k in own):,}, "
        f"N {sum(k['ident'] == 'N' for k in own):,}")
    t1 = [k for k in own if k["ident"] == "Y" and k["priced"]]
    any_t = [k for k in own if k["priced"]]
    say(f"- R1 input (own + ticker Y + price stated): {len(t1):,}; own + price stated at ANY ticker reading (the freeze record's 'incl. amb', which "
        f"counts N too): {len(any_t):,} = Y {sum(k['ident'] == 'Y' for k in any_t)} + amb {sum(k['ident'] == 'amb' for k in any_t)} + N "
        f"{sum(k['ident'] == 'N' for k in any_t)} (printed, never scored)")
    clean_fills = [k for k in t1 if k["fill"] == "fill" and not k["garbled"]]
    say(f"- of the R1 input: clean {sum(not k['garbled'] for k in t1):,} / garbled {sum(k['garbled'] for k in t1):,} (R64); "
        f"fill {sum(k['fill'] == 'fill' for k in t1):,} / level {sum(k['fill'] == 'level' for k in t1):,} (R63); clean fills {len(clean_fills):,}")
    say(f"- of the clean fills (R85, by the reader's labels): price kind matching the action's side {sum(k['matched'] for k in clean_fills):,} "
        f"(holding/entry or side-mismatched {sum(not k['matched'] for k in clean_fills):,}); of the matched, day class naming a day "
        f"{sum(k['matched'] and k['day_named'] for k in clean_fills):,} (unstated / approx_earlier {sum(k['matched'] and not k['day_named'] for k in clean_fills):,}) "
        f"= the primary population BEFORE the join: {sum(K.is_primary_class(k) for k in t1):,}")
    say("- R1 input by action x price kind: " + ", ".join(f"{a}/{pk} {n}" for (a, pk), n in sorted(collections.Counter((k["action"], k["price_kind"]) for k in t1).items())))
    say("- R1 input by day class: " + ", ".join(f"{d} {n}" for d, n in sorted(collections.Counter(k["day_class"] for k in t1).items())))
    tr = K.t1_readings(t1)
    say(f"- T1 under each reading (R65): the freeze record's (own + ticker Y + price stated) {tr['freeze_record']}; §4.1's tier words (an event action + a "
        f"day class that names a day) {tr['s41_words']}; with approx_earlier {tr['s41_with_approx']}; with stop_level too {tr['s41_with_approx_and_stop_level']}. "
        f"The §9 floor ({K.T1_FLOOR}) is read on the SCORED primary n in the run, never on these; every §4.1 reading sits "
        f"{'under' if max(v for k, v in tr.items() if k != 'freeze_record') < K.T1_FLOOR else 'at or over'} {K.T1_FLOOR}, the freeze record's "
        f"{'clears it by ' + str(tr['freeze_record'] - K.T1_FLOOR) if tr['freeze_record'] >= K.T1_FLOOR else 'sits under it too'}")
    say(f"- R4 input (shares AND a dollar result on one own-trade statement): {sum(1 for k in own if k['shares'] and k['dollar_result'] is not None):,} (R71)")
    say(f"- ranges.tsv: {len(ranges):,} sides; buys {sum(1 for (_e, sd) in ranges if sd == 'buy'):,}, sales {sum(1 for (_e, sd) in ranges if sd == 'sale'):,}; "
        f"in-span buys {sum(1 for r in ranges.values() if r['side'] == 'buy' and r['in_span'] == 'True'):,}, sales "
        f"{sum(1 for r in ranges.values() if r['side'] == 'sale' and r['in_span'] == 'True'):,}")
    eids = collections.defaultdict(set)
    for (e, sd) in ranges:
        eids[e].add(sd)
    say(f"- round trips (both sides in ranges.tsv): {sum(1 for v in eids.values() if len(v) == 2):,}")
    jc = join_counts(stmts)
    say(f"\n## The join (symbol and day only; R62: the stream date for every day class)")
    say(f"- own-trade, ticker-identified statements: {jc['n']:,} -> joined (unique) {jc['unique']:,} / ambiguous {jc['ambiguous']:,} "
        f"(of which one position's two windows {jc['ambiguous_one_position']:,}) / no window {jc['none']:,} " +
        "(" + ", ".join(f"{k} {v}" for k, v in sorted(jc["none_reasons"].items())) + ")")
    jr1 = join_counts([s for s in stmts if is_r1_input(s)])
    say(f"- of the R1 input: joined {jr1['unique']:,} / ambiguous {jr1['ambiguous']:,} (one position's two windows {jr1['ambiguous_one_position']:,}) / "
        f"no window {jr1['none']:,} (" + ", ".join(f"{k} {v}" for k, v in sorted(jr1["none_reasons"].items())) + f"); with a range "
        f"{sum(1 for s in stmts if is_scorable(s)):,}; clean fills {sum(1 for s in stmts if is_clean_fill(s)):,}: "
        f"PRIMARY (matched kind, named day; R85) {sum(1 for s in stmts if is_primary(s)):,}, beside: holding/entry or side-mismatched "
        f"{sum(1 for s in stmts if is_unmatched_fill(s)):,}, unstated / approx day {sum(1 for s in stmts if is_unnamed_day_fill(s)):,}; "
        f"garbled line {sum(1 for s in stmts if is_garbled_line(s)):,}; level line {sum(1 for s in stmts if is_level_line(s)):,}")
    say("- the primary by action x price kind x day class: " + ", ".join(f"{a}/{pk}/{dc} {n}" for (a, pk, dc), n in sorted(
        collections.Counter((s["action"], s["price_kind"], s["day_class"]) for s in stmts if is_primary(s)).items())))
    n_prim = sum(1 for s in stmts if is_primary(s))
    say(f"- the §9 floor (R65) on the scored n: primary {n_prim} {'>=' if n_prim >= K.T1_FLOOR else '<'} {K.T1_FLOOR}: the gap bar will read "
        f"{'a verdict' if n_prim >= K.T1_FLOOR else 'NOT DECIDABLE, the would-be verdict beside'} (no share is computed in a dry run)")
    say("- joined R1 input by day class: " + ", ".join(f"{d} {n}" for d, n in sorted(collections.Counter(s["day_class"] for s in stmts if is_r1_input(s) and s["join_status"] == "unique").items())))
    say("- joined R1 input by bracket: " + ", ".join(f"{b} {n}" for b, n in sorted(collections.Counter(s["bracket"] for s in stmts if is_r1_input(s) and s["join_status"] == "unique").items())))
    say(f"- joined R1 input with pre_market_possible: {sum(1 for s in stmts if is_r1_input(s) and s['join_status'] == 'unique' and s['pre_market_possible']):,}")
    say(f"- distinct (position, side, price) among the primary: {len({(s['eid'], s['side'], s['price_raw']) for s in stmts if is_primary(s)}):,} (R73)")
    say("- joined own-trade statements by action: " + ", ".join(f"{a} {n}" for a, n in sorted(collections.Counter(s["action"] for s in stmts if s["join_status"] == "unique").items())))
    say(f"- R5 population (joined, action with a side): {sum(1 for s in stmts if s['join_status'] == 'unique' and s['action'] in K.SIDE_OF_ACTION):,}; "
        f"excluded (holding / stop_level / result): {sum(1 for s in stmts if s['join_status'] == 'unique' and s['action'] not in K.SIDE_OF_ACTION):,} (R72)")
    say("- R3 population (R70): the joined own-trade rows of the v2 PRICE batch only; the T2 batches (reader1_rest_b01-16) are not yet labelled, so T2 proper is NOT read here")
    if claims is not None:
        say("\n## Claims (the freeze record and the plan)")
        claims("v2 price batch rows (freeze record: 434)", 434, len(rows))
        claims("R1 input: own + ticker Y + price stated (freeze record: 102)", 102, len(t1))
        claims("own + price stated at any ticker reading (freeze record: 174 'incl. amb')", 174, len(any_t))
        # R89: ranges.tsv against the LOADED windows (the v2 windows since re-run 2); §3.1's figures are the pre-fix facts, printed beside
        ws = windows or []
        wb, wsale = [w for w in ws if w[1] == "buy"], [w for w in ws if w[1] == "sale"]
        in_span = lambda w: P.SPAN[0] <= w[4] <= P.SPAN[1]
        w_eids = collections.defaultdict(set)
        for w in ws:
            w_eids[int(w[0])].add(w[1])
        missing, extra, differ = K.ranges_vs_windows(ranges, ws)
        say(f"- ranges.tsv against the loaded windows (R89): ranges keys with no window {len(missing)}, windows with no ranges row {len(extra)}, "
            f"keys matched whose (sym, lo, hi) differ from the window's {len(differ)} (review F5)"
            + (f" — e.g. {missing[:3]} / {extra[:3]} / {differ[:3]}" if missing or extra or differ else "")
            + "; the pre-fix facts (§3.1, the original windows): 1,861 sides each way, 1,511 / 1,538 in span, 1,848 round trips")
        claims("ranges.tsv sides = the loaded windows", len(ws), len(ranges))
        claims("buy sides = the loaded buy windows", len(wb), sum(1 for (_e, sd) in ranges if sd == "buy"))
        claims("sale sides = the loaded sale windows", len(wsale), sum(1 for (_e, sd) in ranges if sd == "sale"))
        claims("in-span buy windows = the loaded in-span buys", sum(1 for w in wb if in_span(w)),
               sum(1 for r in ranges.values() if r["side"] == "buy" and r["in_span"] == "True"))
        claims("in-span sale windows = the loaded in-span sales", sum(1 for w in wsale if in_span(w)),
               sum(1 for r in ranges.values() if r["side"] == "sale" and r["in_span"] == "True"))
        claims("round trips = the loaded round trips", sum(1 for v in w_eids.values() if len(v) == 2), sum(1 for v in eids.values() if len(v) == 2))
        claims("every ranges.tsv (eid, side) is a loaded window and every loaded window has a ranges row (R89: one generation)", (0, 0),
               (len(missing), len(extra)))
        claims("every matched ranges.tsv row's (sym, lo, hi) is the loaded window's (R89, review F5: the key check alone passes a subset generation)",
               0, len(differ))
        claims("joined + ambiguous + none = the statements", jc["n"], jc["unique"] + jc["ambiguous"] + jc["none"])
        claims("the join never reads the action or a price (02_captions.join_position signature)",
               ["symbol", "day", "by_sym", "S"], list(CAP.join_position.__code__.co_varnames[:CAP.join_position.__code__.co_argcount]))
    return {"t1": len(t1), "jc": jc}


def consistency_claim(stmts: list, ranges: dict, engine, S, claims) -> int:
    """The engine that ranges the controls reproduces ranges.tsv's raw range on every joined side (so the controls are read the same way)."""
    bad = []
    seen = set()
    for s in stmts:
        if s["join_status"] != "unique" or s["range_lo_raw"] == "" or (s["eid"], s["side"]) in seen:
            continue
        seen.add((s["eid"], s["side"]))
        w0 = K.shifted_window(s["window"], 0, S)
        rng = engine.range_row(w0)
        rr = K.raw_range(rng)
        if rr is None or abs(rr[0] - float(s["range_lo_raw"])) > 1e-3 or abs(rr[1] - float(s["range_hi_raw"])) > 1e-3:
            bad.append((s["eid"], s["side"], rr, s["range_lo_raw"], s["range_hi_raw"]))
    if claims is not None:
        claims(f"the control engine reproduces ranges.tsv's raw range on the {len(seen)} joined sides (mismatches)", 0, len(bad))
    return len(bad)


def report_controls(say, stmts: list, controls: list) -> None:
    cp = control_populations(stmts, controls)
    say("\n## Control populations (built, not scored in a dry run)")
    say(f"- statements with controls: {cp['statements']:,}; with at least one shifted window ranged {cp['with_any_shift']:,}, with all six {cp['with_all_six']:,}; "
        f"with at least one cross name {cp['with_any_cross']:,} (median cross names {cp['cross_names_median']})")
    say(f"- control rows: shifted {sum(1 for c in controls if c['control'] == 'shifted'):,} (ranged {sum(1 for c in controls if c['control'] == 'shifted' and c['range_lo_raw'] != ''):,}), "
        f"cross {sum(1 for c in controls if c['control'] == 'cross'):,} (ranged {sum(1 for c in controls if c['control'] == 'cross' and c['range_lo_raw'] != ''):,})")


def splits_of(stmts: list) -> list:
    """The §4.2 splits: 2020 / 2021-22, with / without flickers, with / without daily-only sources."""
    return [("all", stmts), ("2020", [s for s in stmts if K.year_block(s["year"]) == "2020"]), ("2021-22", [s for s in stmts if K.year_block(s["year"]) == "2021-22"]),
            ("without flickers", [s for s in stmts if s["flicker"] != "True"]), ("flickers only", [s for s in stmts if s["flicker"] == "True"]),
            ("without daily-only", [s for s in stmts if s["resolution"] != "daily_only"]), ("daily-only only", [s for s in stmts if s["resolution"] == "daily_only"])]


def report_scores(say, stmts: list, ranges: dict, n_t1: int, S, by_sym: dict = None) -> dict:
    prim = [s for s in stmts if is_primary(s)]
    say("\n## R1 containment (the primary: clean fills, kind matching the action's side, a named day — R85; bars-only range; raw price; §4.2 tolerance)")
    main = r1_block(prim)
    rows = [r1_row(name, r1_block(ss), bar=(name == "all")) for name, ss in splits_of(prim)]
    table(say, R1_HDR, rows)
    say(f"- the §9 floor is read on the SCORED n (R65): primary n = {main['n']} {'>=' if main['n'] >= K.T1_FLOOR else '<'} {K.T1_FLOOR}; T1 per the "
        f"freeze record = {n_t1}; a 95% interval on a share near 70% at n = {main['n']} is about ±{fmt(196.0 * (0.21 / max(1, main['n'])) ** 0.5)} points "
        f"(the plan priced ±9 at n = 100-250); only the 'all' line is the bar, every other row is beside")
    say("\n### R1 by bracket type (pre_market_possible on its own line; no separate bar)")
    rows = []
    for b in P.BRACKETS:
        ss = [s for s in prim if s["bracket"] == b and not s["pre_market_possible"]]
        if ss:
            rows.append(r1_row(f"{b} ({BRACKET_WORDS.get(b, b)})", r1_block(ss)))
    rows.append(r1_row("pre_market_possible (any bracket)", r1_block([s for s in prim if s["pre_market_possible"]])))
    table(say, R1_HDR, rows)
    say("\n### R1 beside (no bar): the clean fills outside the primary by the reader's labels (R85), the garbled prices, the levels (R63)")
    table(say, R1_HDR, [r1_row("holding/entry or side-mismatched fills", r1_block([s for s in stmts if is_unmatched_fill(s)])),
                        r1_row("matched fills, unstated / approx day", r1_block([s for s in stmts if is_unnamed_day_fill(s)])),
                        r1_row("garbled fills", r1_block([s for s in stmts if is_garbled_line(s)])),
                        r1_row("levels (stop / other / stop_level / result)", r1_block([s for s in stmts if is_level_line(s)]))])
    say("- beside rows by action x price kind: " + "; ".join(
        f"{name}: " + (", ".join(f"{a}/{pk} {n}" for (a, pk), n in sorted(collections.Counter((s["action"], s["price_kind"]) for s in ss).items())) or "(none)")
        for name, ss in (("holding/entry or side-mismatched", [s for s in stmts if is_unmatched_fill(s)]),
                         ("unstated / approx day", [s for s in stmts if is_unnamed_day_fill(s)]))))
    say("\n### The primary statements outside the range (kept, anchored on the stated price, flagged stated_outside_range)")
    outs = [s for s in prim if s["inside"] is False]
    table(say, ["stmt", "date", "ticker", "action", "price", "range raw", "tol", "bracket", "day class", "shifted", "cross"],
          [[s["stmt_id"], s["stream_date"], s["ticker"], s["action"], s["price_raw"], f"{s['range_lo_raw']}-{s['range_hi_raw']}", s["tolerance"], s["bracket"],
            s["day_class"], s["shifted_inside"], f"{s['cross_share']}% (n {s['cross_n']})"] for s in outs] or [["(none)"] + [""] * 10])
    say("\n### Beside, never in the bar — the R1-input statements the one-session join cannot place (R82 mid-hold: the hold's two windows; R83 a "
        "day-trade tie: the position's two windows), clean fills, the price against each window")
    bes = [s for s in stmts if s["beside_eid"] and is_r1_input(s) and s["fill"] == "fill" and not s["garbled"] and (s["beside_buy"] != "" or s["beside_sale"] != "")]
    for name, ss in (("mid-hold (R82)", [s for s in bes if s["join_reason"] == "inside_hold"]), ("one-position tie (R83)", [s for s in bes if s["join_status"] == "ambiguous"])):
        say(f"- {name}: n {len(ss)}; inside the buy window {pct(sum(1 for s in ss if s['beside_buy'] is True), sum(1 for s in ss if s['beside_buy'] != ''))}, "
            f"inside the sale window {pct(sum(1 for s in ss if s['beside_sale'] is True), sum(1 for s in ss if s['beside_sale'] != ''))}, inside either "
            f"{pct(sum(1 for s in ss if s['beside_buy'] is True or s['beside_sale'] is True), len(ss))}; by action: "
            + ", ".join(f"{a} {n}" for a, n in sorted(collections.Counter(s["action"] for s in ss).items())))
    # R3
    say("\n## R3 day offset (stated day - window start / end, in sessions) by the reader's day class — the shape is the readout")
    joined = [s for s in stmts if s["join_status"] == "unique"]
    rows = []
    for dc in K.DAY_CLASSES:
        ss = [s for s in joined if s["day_class"] == dc]
        if not ss:
            continue
        cs, ce = collections.Counter(s["offset_start"] for s in ss), collections.Counter(s["offset_end"] for s in ss)
        rows.append([dc, len(ss), " ".join(f"{k:+d}:{cs[k]}" for k in sorted(cs)), " ".join(f"{k:+d}:{ce[k]}" for k in sorted(ce)),
                     pct(sum(1 for s in ss if s["offset_start"] >= 0 >= s["offset_end"]), len(ss))])
    table(say, ["day class", "n", "day - start (sessions:count)", "day - end", "inside the window (secondary)"], rows)
    say("- a -1 among stream_day statements is next-morning talk (a reader dating question); a window is re-read only if RESOLVED-day statements sit one session off")
    say("\n### R3 beside (secondary, R88): the `other_date` statements — the one-session join never placed them — and the signed distance in sessions "
        "to the NEAREST window of their name (negative: before its start; positive: after its end)")
    od = [s for s in stmts if s["join_status"] == "none" and s["join_reason"] == "other_date" and s["nearest_offset"] != ""]
    rows = []
    for dc in K.DAY_CLASSES:
        ss = [s for s in od if s["day_class"] == dc]
        if ss:
            co = collections.Counter(int(s["nearest_offset"]) for s in ss)
            rows.append([dc, len(ss), " ".join(f"{k:+d}:{co[k]}" for k in sorted(co)), fmt(statistics.median(abs(int(s["nearest_offset"])) for s in ss), 0),
                         pct(sum(1 for s in ss if abs(int(s["nearest_offset"])) <= 5), len(ss))])
    table(say, ["day class", "n", "nearest window offset (sessions:count)", "median |offset|", "within 5 sessions"], rows or [["(none)", 0, "", "", ""]])
    say(f"- {len(od)} other_date statements of the price batch ({sum(1 for s in od if is_r1_input(s))} in the R1 input); a spread wider than the windows here "
        "means the caption dating is loose (§4.2), not a late window")
    # R4
    say("\n## R4 implied move (dollar result / shares, % of the entry price) against the trade's band of outcomes")
    anc = anchors(stmts)
    r4 = []
    for s in joined:
        if s["shares"] == "" or s["dollar_result"] == "":
            continue
        eid = int(s["eid"])
        b, x = ranges.get((eid, "buy")), ranges.get((eid, "sale"))
        if not b or not x or K.raw_range(b) is None or K.raw_range(x) is None:
            r4.append([s["stmt_id"], s["ticker"], s["shares"], s["dollar_result"], "n/a", "n/a", "no band (a side has no range)"])
            continue
        a = anc.get((eid, "buy"))
        entry = a["price_raw"] if a else (float(b["avg_traded_price_raw"]) if b["avg_traded_price_raw"] not in ("", None) else None)
        mv = K.implied_move(float(s["dollar_result"]), float(s["shares"]), entry) if entry else None
        lo, hi = K.outcome_band(*K.raw_range(b), *K.raw_range(x))
        inside = None if mv is None else (lo <= mv <= hi)
        r4.append([s["stmt_id"], s["ticker"], s["shares"], s["dollar_result"], fmt(mv), f"{fmt(lo)}..{fmt(hi)}", "" if inside is None else ("inside" if inside else "outside")])
    table(say, ["stmt", "ticker", "shares", "dollars", "implied move %", "band %", "verdict"], r4 or [["(none)"] + [""] * 6])
    n4 = sum(1 for r in r4 if r[6] in ("inside", "outside"))
    say(f"- n = {n4}: the 70% bar is printed, not read, at this n (R71): {pct(sum(1 for r in r4 if r[6] == 'inside'), n4)} inside")
    # R5
    say("\n## R5 side agreement (the join never saw the action)")
    r5 = K.r5_agreement([(s["action"], s["side"]) for s in joined])
    say(f"{K.LINE_R5}{r5['verdict']} — {r5['agree']} / {r5['n']} = {pct(r5['agree'], r5['n'])} agree (bar >= 90%); excluded, no side: {r5['excluded_no_side']}")
    for name, ss in splits_of(joined):
        rr = K.r5_agreement([(s["action"], s["side"]) for s in ss])
        say(f"  - {name}: {rr['agree']} / {rr['n']} = {pct(rr['agree'], rr['n'])}")
    miss = [s for s in joined if s["r5_agree"] is False]
    table(say, ["stmt", "date", "ticker", "action", "landed side", "dist", "day class"],
          [[s["stmt_id"], s["stream_date"], s["ticker"], s["action"], s["side"], s["dist"], s["day_class"]] for s in miss] or [["(none)"] + [""] * 6])
    # anchors
    say("\n## Anchors (R73, R74): the mean clean fill price per (position, side); ranges.tsv is not written")
    say(f"- anchored sides: {len(anc)}; outside the range: {sum(1 for a in anc.values() if a['outside'])}; several statements: "
        f"{sum(1 for a in anc.values() if a['n'] > 1)}, of which differing beyond the tolerance: {sum(1 for a in anc.values() if a['differ'])}")
    # the consequence table
    say("\n## Consequence table (§4.2, the labels verbatim)")
    say(f"{K.LINE_R1}{main['verdict']} — gap over the shifted-window control {fmt(main['gap_shifted'])} points, over the cross-symbol control "
        f"{fmt(main['gap_cross'])} points (bar >= 25 each); n_T1 = {n_t1}, primary n = {main['n']}"
        + (f"; would read {main['would_be']} at a decidable n" if main["verdict"] == K.VERDICT_ND and main["would_be"] else ""))
    say(f"- {main['label']}")
    if main["verdict"] == K.VERDICT_PASS:
        say(f"- {K.LABEL_OUTSIDE_KEPT} ({len(outs)} statements, {sum(1 for a in anc.values() if a['outside'])} sides)")
    if r5["verdict"] != K.VERDICT_PASS:
        say(f"- {K.LABEL_R5_FAIL}")
    dens = [float(r["density_all"]) for r in ranges.values() if r.get("density_all") not in ("", None)]
    med = statistics.median(dens) if dens else None
    say(f"- density (§3.3, ranges.tsv density_all median {fmt(med, 3)} over {len(dens):,} sides, line {P.DENSITY_LINE}): "
        + (K.LABEL_DENSITY_ND if (med is not None and med > P.DENSITY_LINE) else "'where he acts' is readable for the full set"))
    return {"r1": main, "r5": r5, "anchors": anc}


# ═════════════════════════════════════════════════════════════════════════════════════════════
# main
# ═════════════════════════════════════════════════════════════════════════════════════════════
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--print-pins", action="store_true")
    g.add_argument("--run", action="store_true")
    g.add_argument("--archive", action="store_true", help="R90: move 6b's first-run files to *_run1 with ledger rows")
    a = ap.parse_args(argv)
    if a.print_pins:
        lines = [f"{k}\t{v}" for k, v in K.pins_6b().items()]
        print("\n".join(lines))
        with open(K.P03["pins"], "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
        print(f"(written to {K.P03['pins']})")
        return 0
    if a.archive:
        try:
            moved = C.archive_files(K.archive_items_6b(), K.ARCHIVE_SUFFIX_6B, K.ARCHIVE_STAGE_6B)
        except K.GuardStop as ex:
            print(f"REFUSED: {ex}")
            return 3
        for path, arc, s in moved:
            print(f"archived {path} -> {arc} ({s[:16]}); ledger row {K.ARCHIVE_STAGE_6B}*")
        bad = C.ledger_verify()
        print("ledger verifies" if not bad else "LEDGER PROBLEMS: " + "; ".join(bad))
        return 0 if not bad else 3
    say = Say()
    refused_to = K.P03["dry"] if a.dry_run else K.P03["refused"]
    if not K.preamble(say, "6b (the check against his words)", "DRY RUN" if a.dry_run else "RUN", SCAN_FILES, K.MODULE_FILES_6B, refused_to):
        return 2
    if a.run:
        problems = K.run_gate("6b")
        if problems:
            for pr in problems:
                say("REFUSED: " + pr)
            say.write(K.P03["refused"])
            return 3
        say("- run gates: the dry run completed with 0 MISMATCH by these modules; every pin (inputs, modules, doc body, the dry-run printout) is below "
            "the doc's freeze marker; the ledger verifies; no output exists")
    say("\n## Inputs")
    rows = K.read_sheets()
    say(f"- sheets: " + ", ".join(f"{os.path.basename(p)} {C.sha(p)[:16]}" for p in K.V2_SHEETS) + f"; wording v2 {C.sha(K.WORDING_V2)[:16]}")
    if not os.path.exists(K.RANGES):                                   # R90: step 5's re-run has not written its ranges yet
        say(f"STOPPED: ranges.tsv is absent ({K.RANGES}) — step 5's re-run 2 has not run; 6b reads the windows' ranges and cannot be dry-run "
            "before it (order: 01 --run, then 03 --dry-run, --print-pins, paste, --run)")
        say.write(refused_to)
        return 2
    ranges = K.read_ranges()
    say(f"- ranges.tsv {C.sha(K.RANGES)[:16]} ({len(ranges):,} sides; its stated_* columns stay blank, R74)")
    tally = collections.Counter()
    L = P.load_all(say, tally)
    P.preload_minutes(L, say)
    engine = K.RangeEngine(L)
    S = L["S"]
    windows = K.windows_tuple(L["buys"] + L["sales"])
    by_sym, holds = CAP.index_windows(windows), CAP.index_holds(windows)
    say(f"- windows: {len(windows):,} (the readers' tickers are joined to the panel symbol)")
    stmts = build_statements(rows, by_sym, holds, ranges, engine, S)
    claims = Claims(say) if a.dry_run else None
    pop = report_populations(say, rows, stmts, ranges, claims, windows)
    consistency_claim(stmts, ranges, engine, S, claims)
    controls = build_controls(stmts, by_sym, ranges, engine, S, say)
    report_controls(say, stmts, controls)
    beside_table(say, stmts, ranges, engine, S)
    if a.dry_run:
        say("")
        say(claims.result())
        say("DRY RUN COMPLETE")
        say.write(K.P03["dry"])
        return 0
    score(stmts, controls, ranges, engine, S)
    res = report_scores(say, stmts, ranges, pop["t1"], S, by_sym)
    anc = res["anchors"]
    for s in stmts:
        a_ = anc.get((int(s["eid"]), s["side"])) if s["join_status"] == "unique" else None
        s["primary"] = is_primary(s)
        s["anchor_price_raw"], s["anchor_price_bar"] = (a_["price_raw"], a_["price_bar"]) if a_ else ("", "")
        s["stated_outside_range"] = (s["inside"] is False) if is_primary(s) else ""          # R86: this statement's own price
        s["side_outside_range"] = a_["outside"] if a_ else ""                                 # R86: any primary statement on the side
        s["flags"] = "|".join(x for x in [s.get("flags", ""), "anchors_differ" if (a_ and a_["differ"]) else ""] if x)
    K.write_tsv(stmts, CHECK_COLS, K.OUT_6B["check_r1_r5"])
    K.write_tsv(controls, CONTROL_COLS, K.OUT_6B["control_ranges"])
    say("\n## Outputs")
    for k, p in K.OUT_6B.items():
        say(f"- {k}: {p} ({C.sha(p)[:16]})")
    say("RUN COMPLETE")
    say.write(K.P03["run"])
    C.ledger_append(K.STAGE_6B + "dry_run", K.P03["dry"])
    C.ledger_append(K.STAGE_6B + "check", K.P03["run"])
    for k, p in K.OUT_6B.items():
        C.ledger_append(K.STAGE_6B + k, p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
