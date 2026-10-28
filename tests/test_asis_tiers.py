"""Tests for the #711 as-is read, step 7 part 1 — the confidence tiers (scripts/probes/_705_asis_1026/05_tiers.py; the registration
docs/analysis/cb_asis_step7_grouping_prereg_2026-10-27.md §10). Synthetic fixtures only: no apollo_data, no machine path; the one real-data
dry run carries a skip guard naming the data.

Covers: `tier_of` on hand-built sides — every tier and every LOW reason, and the ORDER (a flicker with tight minute sides is ONE-STREAM; a
wide, rangeless, inverted, `bracket_other` or missing side is LOW whatever the stream count); the disclosed 3-position fork (a single-stream
NON-flicker with near sides is MEDIUM and flagged `single_stream_nonflicker`); `confirmed_flags` (a stop LEVEL inside the range never
confirms; `r5_agree` alone confirms; the primary sub-count); `population` (in span by the BUY side only; a sale out of span is kept);
`assign_all`'s columns and the composition buckets; the identifier scan with BOTH name lists (a planted outcome name fails, the module is
clean); the fresh-interpreter import belt; the run gate (no dry run, a MISMATCH, a pin above the marker, an ABSENT stage pin, an existing
output, a two-marker doc each refuse; the complete case passes); the registration's single marker and the tier wording verbatim; the
real-data dry run ends DRY RUN COMPLETE with 0 MISMATCH and writes no output. After the 2026-10-27 review: the step-7 feature registration
(no `ret_N` on the exit side, no `our_length` column in the primary set, the exit look-back rule by hold length), the per-statement file
loaded through `usecols` (its stated-dollar column never in memory), the outcome-name list carrying 04_band's and 03_check's names, the
price facet keyed on the side's resolution.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
ASIS = REPO / "scripts" / "probes" / "_705_asis_1026"
DOC7 = REPO / "docs" / "analysis" / "cb_asis_step7_grouping_prereg_2026-10-27.md"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


T = _load("asis_tiers05", ASIS / "05_tiers.py")
C = T.C

REAL_DATA = os.path.exists(C.OUTPUTS["ranges"]) and os.path.exists(C.FILES["entries_v2"]) and os.path.exists(T.CHECK_R1_R5)
needs_real_data = pytest.mark.skipif(not REAL_DATA, reason="needs the local apollo_data cb702/qm_streams/asis_1026 tree (ranges.tsv, "
                                                            "windows_v2/entries_v2.tsv, check_r1_r5.tsv)")


# ═════════════════════════════════════════════════════════════════════════════════════════════ fixtures
def side(bracket="same_in_in", resolution="minute", lo="2020-06-01", hi="2020-06-01", has_range=True, inverted=False, n_sessions="1",
         eid="1", sym="AAA", sd="buy", in_span="True", year="2020", flicker="False", width="2.5", price_raw="42.0", flags="", hold="3"):
    return {"eid": eid, "sym": sym, "side": sd, "year": year, "in_span": in_span, "flicker": flicker, "inverted": str(inverted),
            "bracket": bracket, "lo": lo, "hi": hi, "n_sessions": n_sessions, "resolution": resolution,
            "range_lo": "40.0" if has_range else "", "range_hi": "44.0" if has_range else "", "range_width_pct": width if has_range else "",
            "avg_traded_price_raw": price_raw if has_range else "", "hold_sessions_min": hold, "hold_sessions_max": hold, "flags": flags}


def entry(eid="1", flicker="False", n_streams="3", n_sightings="7"):
    return {"eid": eid, "flicker": flicker, "n_streams": n_streams, "n_sightings": n_sightings}


def stmt(eid="1", r5="", inside="", fill="fill", primary="False", join="unique"):
    return {"stmt_id": f"s{eid}", "eid": eid, "r5_agree": r5, "inside": inside, "fill": fill, "primary": primary, "join_status": join}


# ═════════════════════════════════════════════════════════════════════════════════════════════ tier_of
def test_high_needs_tight_minute_both_sides_and_no_flicker():
    assert T.tier_of(side(), side(sd="sale", bracket="next_in_pre"), flicker=False) == ("HIGH", "tight_minute_both")
    assert T.tier_of(side(bracket="next_in_in"), side(sd="sale", bracket="same_pre_in"), False)[0] == "HIGH"
    # one side daily-only -> MEDIUM, not HIGH
    assert T.tier_of(side(), side(sd="sale", resolution="daily_only"), False) == ("MEDIUM", "near_with_range")
    # one side 2-5 sessions -> MEDIUM
    assert T.tier_of(side(), side(sd="sale", bracket="sessions_2_5", n_sessions="3"), False) == ("MEDIUM", "near_with_range")
    assert T.tier_of(side(bracket="sessions_2_5"), side(sd="sale", bracket="sessions_2_5"), False)[0] == "MEDIUM"


def test_flicker_never_reads_high_or_medium():
    assert T.tier_of(side(), side(sd="sale"), flicker=True) == ("ONE-STREAM", "flicker")
    assert T.tier_of(side(bracket="sessions_2_5"), side(sd="sale", resolution="daily_only"), True) == ("ONE-STREAM", "flicker")


@pytest.mark.parametrize("buy,sale,reason", [
    (side(bracket="sessions_6plus", n_sessions="9"), side(sd="sale"), "wide_window"),
    (side(), side(sd="sale", bracket="sessions_6plus", n_sessions="7"), "wide_window"),
    (side(bracket="next_other"), side(sd="sale"), "bracket_other"),
    (side(), side(sd="sale", bracket="same_other"), "bracket_other"),
    (side(has_range=False, resolution="none"), side(sd="sale"), "no_range"),
    (side(), side(sd="sale", has_range=False, resolution="none"), "no_range"),
    (side(bracket="inverted", inverted=True, has_range=False, resolution=""), side(sd="sale"), "inverted"),
    (side(), None, "sale_missing"),
])
def test_low_reasons_apply_whatever_the_stream_count(buy, sale, reason):
    assert T.tier_of(buy, sale, flicker=False) == ("LOW", reason)
    assert T.tier_of(buy, sale, flicker=True) == ("LOW", reason)          # a flicker with a LOW side is LOW, not ONE-STREAM


def test_inverted_outranks_no_range_and_wide_outranks_bracket_other():
    assert T.tier_of(side(bracket="inverted", inverted=True, has_range=False), side(sd="sale", has_range=False), False)[1] == "inverted"
    assert T.tier_of(side(bracket="sessions_6plus"), side(sd="sale", bracket="next_other"), False)[1] == "wide_window"


# ═════════════════════════════════════════════════════════════════════════════════════════════ the fork, population, assign_all
def test_single_stream_nonflicker_with_near_sides_is_medium_and_flagged():
    ranges = [side(eid="7"), side(eid="7", sd="sale", bracket="sessions_2_5", n_sessions="4")]
    rows = T.assign_all(ranges, {"7": entry("7", flicker="False", n_streams="1")}, [])
    assert len(rows) == 1 and rows[0]["tier"] == "MEDIUM" and rows[0]["single_stream_nonflicker"] is True
    # the same screen facts with the flicker flag set: ONE-STREAM, not flagged
    rows = T.assign_all(ranges, {"7": entry("7", flicker="True", n_streams="1")}, [])
    assert rows[0]["tier"] == "ONE-STREAM" and rows[0]["single_stream_nonflicker"] is False
    # seen on two streams: MEDIUM, not flagged
    rows = T.assign_all(ranges, {"7": entry("7", flicker="False", n_streams="2")}, [])
    assert rows[0]["tier"] == "MEDIUM" and rows[0]["single_stream_nonflicker"] is False


def test_population_is_in_span_by_the_buy_side_only():
    ranges = [side(eid="1"), side(eid="1", sd="sale", in_span="False", year="2022"),      # sale out of span: kept
              side(eid="2", in_span="False", year="2019"), side(eid="2", sd="sale", in_span="True"),   # buy out of span: excluded
              side(eid="3")]                                                               # no sale row: kept, LOW
    pop = T.population(ranges)
    assert set(pop) == {"1", "3"} and pop["1"]["sale"]["in_span"] == "False" and pop["3"]["sale"] is None
    rows = T.assign_all(ranges, {"1": entry("1"), "3": entry("3")}, [])
    by = {r["eid"]: r for r in rows}
    assert by["1"]["tier"] == "HIGH" and by["1"]["sale_in_span"] is False
    assert by["3"]["tier"] == "LOW" and by["3"]["tier_reason"] == "sale_missing" and by["3"]["bracket_pair"] == "tight/missing"


def test_assign_all_columns_and_buckets():
    ranges = [side(eid="1", flags="pre_market_possible|extended_hours_possible", price_raw="150.0", hold="12"),
              side(eid="1", sd="sale", bracket="next_in_pre", width="4.0", hold="12")]
    rows = T.assign_all(ranges, {"1": entry("1", n_streams="6", n_sightings="20")}, [stmt("1", r5="True")])
    r = rows[0]
    assert list(r) == T.TIER_COLS
    assert r["pre_market_possible"] is True and r["price_band"] == "$100+" and r["hold_bucket"] == "6-20" and r["minute_coverage"] == "both"
    assert r["confirmed"] is True and r["confirmed_r5"] is True and r["confirmed_r1"] is False
    assert r["buy_range_width_pct"] == "2.5" and r["sale_range_width_pct"] == "4.0" and r["bracket_pair"] == "tight/tight"
    assert T.hold_bucket("0") == "0" and T.hold_bucket("1") == "1" and T.hold_bucket("5") == "2-5" and T.hold_bucket("21") == "21+" and T.hold_bucket("") == "?"
    assert T.streams_bucket("1") == "1" and T.streams_bucket("2") == "2" and T.streams_bucket("5") == "3-5" and T.streams_bucket("9") == "6+"
    assert T.price_band("4.99") == "<$5" and T.price_band("19.99") == "$5-20" and T.price_band("99.9") == "$20-100" and T.price_band("") == "?"
    assert T.minute_coverage(T.side_quality(side(resolution="daily_only")), T.side_quality(side(sd="sale"))) == "one"
    assert T.minute_coverage(T.side_quality(side(resolution="none")), T.side_quality(side(sd="sale", resolution="daily_only"))) == "none"
    comp = T.composition(rows, "HIGH")
    assert ("streams seen on", "6+", 1, "100.0%") in comp and ("confirmed by his words", "True", 1, "100.0%") in comp
    assert T.composition(rows, "LOW") == []


# ═════════════════════════════════════════════════════════════════════════════════════════════ confirmed_flags
def test_confirmed_a_level_inside_the_range_never_confirms_and_r5_alone_does():
    flags = T.confirmed_flags([stmt("1", inside="True", fill="level"),                   # "my stop is 40" inside the range: not a fill
                               stmt("2", inside="True", fill="fill"),
                               stmt("3", inside="True", fill="fill", primary="True"),
                               stmt("4", r5="True"),
                               stmt("5", r5="False", inside="False"),
                               stmt("", r5="True"),                                       # no position: ignored
                               stmt("6", r5="True", inside="True", fill="fill")])
    assert "1" not in flags and "5" not in flags                    # only a confirming statement creates an entry
    assert flags["2"] == {"r5": False, "r1": True, "r1_primary": False}
    assert flags["3"] == {"r5": False, "r1": True, "r1_primary": True}
    assert flags["4"] == {"r5": True, "r1": False, "r1_primary": False}
    assert flags["6"] == {"r5": True, "r1": True, "r1_primary": False} and "" not in flags


# ═════════════════════════════════════════════════════════════════════════════════════════════ guards
def test_identifier_scan_with_both_lists_is_clean_on_the_module_and_fails_on_a_planted_outcome_name(tmp_path):
    forb = T.forbidden_all()
    assert {"result_pct", "gain", "winner", "E", "level_at"} <= forb
    assert C.scan_identifiers([str(ASIS / n) for n in T.SCAN_FILES_7], forb) == []
    planted = tmp_path / "planted.py"
    planted.write_text("average = 1\ngain = 2\nx = 'result_pct'\ny = 'regained'\n", encoding="utf-8")
    assert [t for _p, _l, t in C.scan_identifiers([str(planted)], forb)] == ["gain", "'result_pct'"]


def test_fresh_interpreter_import_holds_no_rule_module_and_no_network_client():
    # `socket` itself arrives with pandas; the belt is on the clients that would open one
    code = ("import importlib.util, json, sys\n"
            f"spec = importlib.util.spec_from_file_location('t05', {str(ASIS / '05_tiers.py')!r})\n"
            "m = importlib.util.module_from_spec(spec); sys.modules['t05'] = m; spec.loader.exec_module(m)\n"
            "mods = set(sys.modules)\n"
            "print(json.dumps({'rule': m.C.rule_modules_loaded(), 'net': sorted(mods & {'requests', 'urllib3', 'http.client', "
            "'anthropic', 'openai', 'psycopg2', 'sqlalchemy'})}))\n")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=180, cwd=str(REPO))
    assert r.returncode == 0, r.stderr[-2000:]
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert out["rule"] == [] and out["net"] == []


# ═════════════════════════════════════════════════════════════════════════════════════════════ the run gate
def _gate_env(tmp_path, monkeypatch, mismatch: int = 0, modules_line: str = None, complete: bool = True) -> dict:
    """A tmp world for run_gate: a dry-run printout, a doc with one marker and every pin pasted below it, tmp outputs, no ledger."""
    d = tmp_path / "w"
    d.mkdir(parents=True)
    paths = {"dry": str(d / "dry.txt"), "run": str(d / "run.txt"), "refused": str(d / "refused.txt"), "pins": str(d / "pins.txt")}
    ml = T.module_shas_line() if modules_line is None else modules_line
    lines = ["# dry", f"- modules: {ml}", f"RESULT: 3 claims, {3 - mismatch} OK, {mismatch} MISMATCH"]
    if complete:
        lines.append("DRY RUN COMPLETE")
    Path(paths["dry"]).write_text("\n".join(lines) + "\n", encoding="utf-8")
    for key in ("ranges", "candidates", "coverage"):
        (d / f"{key}.tsv").write_text("eid\n", encoding="utf-8")
    (d / "check.tsv").write_text("stmt_id\n", encoding="utf-8")
    (d / "03.txt").write_text("run\n", encoding="utf-8")
    monkeypatch.setattr(C, "OUTPUTS", {k: str(d / f"{k}.tsv") for k in ("candidates", "ranges", "coverage")})
    monkeypatch.setattr(T, "CHECK_R1_R5", str(d / "check.tsv"))
    monkeypatch.setattr(T, "P03_RUN", str(d / "03.txt"))
    monkeypatch.setattr(T, "OUT_7", {"tiers": str(d / "tiers.tsv")})
    monkeypatch.setattr(C, "LEDGER", str(d / "no_ledger.tsv"))
    monkeypatch.setattr(C, "subs_list_sha", lambda paths=None: "subs")
    doc = d / "doc.md"
    doc.write_text("# step 7\n\nbody\n\n<!-- FREEZE -->\n## Freeze record\n", encoding="utf-8")
    pins = T.pins_7(str(doc), paths["dry"])
    doc.write_text(doc.read_text(encoding="utf-8") + "\n".join(f"- {k}: {v}" for k, v in pins.items()) + "\n", encoding="utf-8")
    return {"paths": paths, "doc": str(doc), "dir": d}


def test_run_gate_passes_in_a_complete_world(tmp_path, monkeypatch):
    w = _gate_env(tmp_path, monkeypatch)
    assert T.run_gate(w["doc"], w["paths"]) == []


def test_run_gate_refuses_without_a_dry_run_or_with_a_mismatch_or_other_code(tmp_path, monkeypatch):
    w = _gate_env(tmp_path, monkeypatch, complete=False)
    assert any("has not completed" in p for p in T.run_gate(w["doc"], w["paths"]))
    w = _gate_env(tmp_path / "b", monkeypatch, mismatch=1)
    assert any("1 MISMATCH" in p for p in T.run_gate(w["doc"], w["paths"]))
    w = _gate_env(tmp_path / "c", monkeypatch, modules_line="05_tiers.py 0000000000000000")
    assert any("other code" in p for p in T.run_gate(w["doc"], w["paths"]))


def test_run_gate_refuses_a_pin_above_the_marker_an_absent_stage_pin_an_existing_output_and_two_markers(tmp_path, monkeypatch):
    w = _gate_env(tmp_path, monkeypatch)
    doc = Path(w["doc"])
    text = doc.read_text(encoding="utf-8")
    pins = T.pins_7(w["doc"], w["paths"]["dry"])
    # the dry-run pin moved ABOVE the marker: missing below it
    line = f"- dryrun7_printout: {pins['dryrun7_printout']}"
    doc.write_text(text.replace(line + "\n", "").replace("<!-- FREEZE -->", line + "\n<!-- FREEZE -->"), encoding="utf-8")
    assert any("dryrun7_printout" in p and "freeze marker" in p for p in T.run_gate(w["doc"], w["paths"]))
    doc.write_text(text, encoding="utf-8")
    # a stage pin reading ABSENT (the per-statement file deleted): refused even though 'ABSENT' is pasted
    os.remove(T.CHECK_R1_R5)
    pins2 = T.pins_7(w["doc"], w["paths"]["dry"])
    assert pins2["check_r1_r5"] == "ABSENT"
    doc.write_text(text + "- check_r1_r5: ABSENT\n", encoding="utf-8")
    assert any("ABSENT" in p and "check_r1_r5" in p for p in T.run_gate(w["doc"], w["paths"]))
    Path(T.CHECK_R1_R5).write_text("stmt_id\n", encoding="utf-8")
    doc.write_text(text, encoding="utf-8")
    assert T.run_gate(w["doc"], w["paths"]) == []
    # an existing output
    Path(T.OUT_7["tiers"]).write_text("eid\n", encoding="utf-8")
    assert any("outputs exist" in p for p in T.run_gate(w["doc"], w["paths"]))
    os.remove(T.OUT_7["tiers"])
    # two markers: every pin missing
    doc.write_text(text + "<!-- FREEZE -->\n", encoding="utf-8")
    assert any("freeze marker" in p for p in T.run_gate(w["doc"], w["paths"]))
    # a missing doc
    assert any("registration is missing" in p for p in T.run_gate(str(tmp_path / "none.md"), w["paths"]))


def test_stage_pin_keys_are_the_ones_added_after_step5_inputs(tmp_path, monkeypatch):
    w = _gate_env(tmp_path, monkeypatch)
    pins = T.pins_7(w["doc"], w["paths"]["dry"])
    keys = T.stage_pin_keys(pins, w["doc"])
    assert {"doc_body_steps56", "ranges", "candidates", "coverage", "check_r1_r5", "run6b_printout", "05_tiers.py", "forbidden_outcomes.txt",
            "dryrun7_printout", "03_check.py", "asis_check_common.py"} == set(keys)
    assert "doc_body" in pins and "entries_v2" in pins and "doc_body" not in keys


# ═════════════════════════════════════════════════════════════════════════════════════════════ the registration
def test_registration_has_one_marker_the_tier_wording_verbatim_and_passes_the_doc_gate():
    text = DOC7.read_text(encoding="utf-8")
    assert len(C.marker_spans(text.encode())) == 1
    for t in T.TIERS:
        assert T.TIERS_TEXT[t] in text, t
    for t, n in T.PROPOSED.items():
        assert f"n = {n:,}".replace(",", "") in text or f"n = {n}" in text, t
    assert "forbidden_outcomes.txt" in text and "doc_body_steps56" in text
    assert "STEP7_FEATURES" in text and "exit_lookbacks_defined" in text and "no same-session round trip" in text.replace("same-day", "same-session")
    sys.path.insert(0, str(REPO / "scripts"))
    try:
        import check_analysis_doc
    finally:
        sys.path.pop(0)
    assert check_analysis_doc.check(str(DOC7)) == []


# ═════════════════════════════════════════════════════════════════════════════════════════════ real data
@needs_real_data
def test_dry_run_on_real_data_ends_complete_with_zero_mismatch_and_writes_no_output(tmp_path, monkeypatch):
    paths = dict(T.P05)
    paths["dry"] = str(tmp_path / "dry.txt")                      # never the pinned printout
    monkeypatch.setattr(T, "P05", paths)
    monkeypatch.setattr(C, "rule_modules_loaded", lambda: [])    # a shared pytest process may hold other tests' modules; the fresh-interpreter test covers the belt
    before = os.path.exists(T.OUT_7["tiers"])
    assert T.main(["--dry-run"]) == 0
    lines = [ln for ln in Path(paths["dry"]).read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert lines[-1].startswith("DRY RUN COMPLETE") and C.printout_mismatches(paths["dry"]) == 0
    text = "\n".join(lines)
    for t, n in T.PROPOSED.items():
        assert f"tier {t} = the approved count: expected {n}, got {n}" in text
    assert os.path.exists(T.OUT_7["tiers"]) == before           # a dry run writes no tiers.tsv


# ═════════════════════════════════════════════════════════════════════════════════════════════ the 2026-10-27 review (F1 / F2 / F4 / F6)
def test_step7_exit_features_carry_no_ret_and_the_primary_set_no_our_length_column():
    for run, f in T.STEP7_FEATURES.items():
        assert not [c for c in f["exit"] if c.startswith("ret_")], run                 # F1: the exit side never carries the stock's N-session change
        assert f["trade"] == ("hold_sessions_max",)
        assert not (set(f["entry"]) | set(f["exit"])) & set(T.HELD_OUT)
    prim, full = T.STEP7_FEATURES["primary"], T.STEP7_FEATURES["with_our_length"]
    assert not (set(prim["entry"]) | set(prim["exit"])) & T.OUR_LENGTH                   # F4: the primary leans on none of our old lengths
    assert T.OUR_LENGTH <= set(full["entry"]) and {"dist_hi_20", "vol_day_vs_20", "range_vs_avgrange_20", "dist_ma_10"} <= T.OUR_LENGTH
    assert {"ret_3", "ret_60", "dist_hi_40", "dist_ma_13", "vol_day_vs_40", "range_vs_avgrange_5", "sessions_since_hi_60"} <= set(prim["entry"])
    assert "ret_3" in full["entry"] and "ret_3" not in full["exit"]
    assert set(prim["exit"]) <= set(prim["entry"]) and set(full["exit"]) <= set(full["entry"])
    assert len(prim["entry"]) == 40 and len(prim["exit"]) == 34 and len(full["entry"]) == 50 and len(full["exit"]) == 44


def test_exit_lookbacks_defined_only_when_shorter_than_the_minimum_hold_or_a_same_session_round_trip():
    assert T.exit_lookbacks_defined("1", "1") == ()                      # a one-session hold: the prior session is the entry day
    assert T.exit_lookbacks_defined("0", "1") == ()                      # may be the next day: nothing is safely before the entry
    assert T.exit_lookbacks_defined("0", "0") == tuple(sorted(T.LOOKBACKS))   # same-session: every prior session precedes the entry
    assert T.exit_lookbacks_defined("2", "2") == (1,)
    assert T.exit_lookbacks_defined("4", "5") == (1, 3)
    assert T.exit_lookbacks_defined("14", "14") == (1, 3, 5, 8, 10, 13)
    assert T.exit_lookbacks_defined("", "") == () and T.exit_lookbacks_defined("x", "1") == ()
    day_own = T.exit_features_defined("1", "1")
    assert set(day_own) == set(c for c in T.STEP7_FEATURES["primary"]["exit"] if c in T.DAY_OWN) and "dist_prev_close" not in day_own
    assert "dist_prev_close" in T.exit_features_defined("2", "2") and "dist_hi_3" not in T.exit_features_defined("2", "2")
    assert "dist_hi_20" not in T.exit_features_defined("30", "30") and "dist_hi_20" in T.exit_features_defined("30", "30", "with_our_length")


def test_per_statement_file_is_loaded_through_usecols_so_its_other_columns_never_reach_memory(tmp_path, monkeypatch):
    f = tmp_path / "check.tsv"
    f.write_text("stmt_id\teid\tr5_agree\tinside\tfill\tprimary\tdollar_result\taction\tjoin_status\n"
                 "s1\t7\tTrue\t\tfill\tFalse\t12000\tstopped\tunique\n", encoding="utf-8")
    monkeypatch.setattr(C, "checked", lambda p: p)
    rows = T.read_tsv(str(f), T.STMT_COLS)
    assert rows and set(rows[0]) == set(T.STMT_COLS) and "dollar_result" not in rows[0] and "action" not in rows[0]
    assert T.confirmed_flags(rows) == {"7": {"r5": True, "r1": False, "r1_primary": False}}
    assert set(T.read_tsv(str(f))[0]) > set(T.STMT_COLS)                 # without usecols the file's every column would load


def test_forbidden_outcomes_name_the_band_and_check_outcome_columns():
    forb = C.load_forbidden_names(T.FORBIDDEN_OUTCOMES_FILE)
    assert {"dollar_result", "ret_middle", "ret_worst", "ret_best", "ret_anchored", "daily_middle", "result_pct", "winner"} <= forb


def test_price_facet_separates_a_daily_only_side_from_a_side_with_no_bars():
    assert T.price_facet("42.0", "minute") == "$20-100" and T.price_facet("150", "daily_only") == "$100+"
    assert T.price_facet("", "daily_only") == "daily-only (no minute price)"
    assert T.price_facet("", "none") == "no bars" and T.price_facet("", "") == "no range (inverted)"
    assert T.price_facet("", "minute") == "minute, no price"
    rows = T.assign_all([side(eid="1", has_range=False, resolution="none"), side(eid="1", sd="sale")], {"1": entry("1")}, [])
    assert rows[0]["price_band"] == "no bars" and rows[0]["tier"] == "LOW"
    rows = T.assign_all([side(eid="2", resolution="daily_only", price_raw=""), side(eid="2", sd="sale")], {"2": entry("2")}, [])
    assert rows[0]["price_band"] == "daily-only (no minute price)" and rows[0]["tier"] == "MEDIUM"
