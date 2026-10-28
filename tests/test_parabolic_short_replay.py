"""#314 — the parabolic-short five-year replay (scripts/probes/_314_replay_build/; the registration
docs/analysis/parabolic_short_replay_prereg_2026-10-21.md, round 4). SYNTHETIC data only, CI-safe; the one real-data test skips without
/Users/alvinfung/apollo_data.

Covers: the synthetic detector golden (expected values below, written before it was first run), the walk goldens through the export
layout and the runner's own loader (every scenario of the shadow test module's four pure-function classes, derived by recording, never
hand-listed), rule (c) against the shadow's own in-memory harness, the pulls through a fake transport (pagination, the K = 3 truncation,
resume, a 404 recorded as the answer, no network on --dry-run), the runner rules (one calendar per record, no id()-keyed cache, numpy
scalars), the owner / company-key / earlier-issuer / cap / dilution / 8-K units, every gate refusing, the patched constant refusing in the
wrong process, the seal, and one END-TO-END run on a synthetic tree: dry run (0 MISMATCH on the tree's own facts) -> freeze -> STEP 0
derive / climax / features with the pulls written by ps_pull through the fake transport -> pins -> walk -> G8 -> VERDICT MATCH.
"""
from __future__ import annotations

# ── the synthetic detector golden: the plan's seal-safe REFUSING detector check. Written BEFORE the test first ran, from the series'
# construction (ps_goldens.detector_series): (stage, sorted failing checks, days_up_streak). ps_goldens reads this literal and the runner
# refuses STEP 0 and the walk on any difference.
DETECTOR_GOLDEN_EXPECTED = {
    "climax": ("climax", (), 20),
    "streak_2": ("anticipation", ("days_up_streak",), 2),
    "earnings_today": ("anticipation", ("earnings",), 20),
    "gap_1_9pct": ("anticipation", ("gapped_today",), 20),
    "volume_one_under": ("anticipation", ("climax_volume",), 20),
}

import gzip
import inspect
import json
import os
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[1]
BUILD = REPO / "scripts" / "probes" / "_314_replay_build"
if str(BUILD) not in sys.path:
    sys.path.insert(0, str(BUILD))
import ps_common as X  # noqa: E402
import ps_population as PP  # noqa: E402
import ps_features as FT  # noqa: E402
import ps_walk as W  # noqa: E402
import ps_goldens as GD  # noqa: E402
import ps_pull as PL  # noqa: E402
import ps_replay as RP  # noqa: E402
import ps_stages as ST  # noqa: E402

from agents.market_intelligence import parabolic_short_shadow as psh  # noqa: E402
from agents.market_intelligence import parabolic_detector as pdm  # noqa: E402

REAL = Path("/Users/alvinfung/apollo_data")


# ═════════════════════════════════════════════════════════════════════════════════════════════
# 1. the synthetic detector golden
# ═════════════════════════════════════════════════════════════════════════════════════════════
def test_detector_golden_matches_the_values_written_first():
    got = GD.detector_golden_results()
    assert got == DETECTOR_GOLDEN_EXPECTED


def test_detector_golden_named_gate_is_among_the_failing_checks():
    for copy, gate in (("streak_2", "days_up_streak"), ("earnings_today", "earnings"), ("gap_1_9pct", "gapped_today"),
                       ("volume_one_under", "climax_volume")):
        stage, failing, _ = GD.detector_golden_results()[copy]
        assert stage != "climax" and gate in failing, copy


def test_the_runner_reads_the_expected_values_from_this_file_and_refuses_a_difference(monkeypatch):
    assert GD.detector_golden_expected() == DETECTOR_GOLDEN_EXPECTED
    assert GD.detector_golden_check(lambda *_: None) == []
    bad = dict(DETECTOR_GOLDEN_EXPECTED, climax=("anticipation", (), 20))
    monkeypatch.setattr(GD, "detector_golden_expected", lambda: bad)
    assert GD.detector_golden_check(lambda *_: None)


# ═════════════════════════════════════════════════════════════════════════════════════════════
# 2. the walk goldens through the export layout and the loader
# ═════════════════════════════════════════════════════════════════════════════════════════════
def test_walk_goldens_registered_numbers_through_the_loader_and_walk_one(tmp_path):
    assert GD.walk_goldens(str(tmp_path), lambda *_: None) == []


def _expand(method):
    marks = [m for m in getattr(method, "pytestmark", []) if m.name == "parametrize"]
    if not marks:
        return [()]
    names, values = marks[0].args[0], marks[0].args[1]
    n = len([x for x in names.split(",") if x.strip()]) if isinstance(names, str) else len(names)
    return [tuple(v) if n > 1 else (v,) for v in values]


def test_every_scenario_of_the_four_pure_classes_is_byte_equal_through_the_export_layout(tmp_path, monkeypatch):
    """R41: the scenarios are DERIVED by running TestGeometry / TestFillConvention / TestArmWindowAndInvalidation / TestManagement with
    replay_episode / trigger_fill / arm_geometry recorded; each is replayed on the fixture dicts and on the dicts the loader returns."""
    T = GD.shadow_tests_module()
    calls = []
    real_replay, real_fill, real_geo = psh.replay_episode, psh.trigger_fill, psh.arm_geometry

    def rec_replay(rows, ci, **kw):
        calls.append(("replay", [dict(r) for r in rows], ci, dict(kw)))
        return real_replay(rows, ci, **kw)

    def rec_fill(level, bar):
        calls.append(("fill", [dict(r) for r in T.market([(bar["open_price"], bar["high_price"], bar["low_price"], bar["close"])])], T.N_HIST,
                      {"stop_price": T.STOP, "armed_on": T.D[0]}))
        return real_fill(level, bar)

    def rec_geo(rows, ci):
        calls.append(("geometry", [dict(r) for r in rows], ci, {"stop_price": T.STOP, "armed_on": rows[ci]["trade_date"]}))
        return real_geo(rows, ci)
    monkeypatch.setattr(psh, "replay_episode", rec_replay)
    monkeypatch.setattr(psh, "trigger_fill", rec_fill)
    monkeypatch.setattr(psh, "arm_geometry", rec_geo)
    ran = 0
    for cls in (T.TestGeometry, T.TestFillConvention, T.TestArmWindowAndInvalidation, T.TestManagement):
        inst = cls()
        for name, fn in inspect.getmembers(cls, inspect.isfunction):
            if not name.startswith("test_"):
                continue
            for params in _expand(fn):
                getattr(inst, name)(*params)
                ran += 1
    monkeypatch.undo()
    assert ran >= 40 and len(calls) >= 40
    dmap = GD.redate_map(T)
    spy = sorted(dmap.values())
    compared = skipped = 0
    for k, (kind, rows, ci, kw) in enumerate(calls):
        if any(r.get(c) is None for r in rows for c in ("open_price", "high_price", "low_price", "close")):
            skipped += 1                               # the data_gap scenario: a None price cannot be written in the layout (by design)
            continue
        fx = GD.redate_rows(rows, dmap)
        kw2 = GD.redate_kwargs(kw, dmap)
        loaded = GD.roundtrip(fx, str(tmp_path / f"s{k}"), spy)
        assert [r["trade_date"] for r in loaded] == [r["trade_date"] for r in fx]
        a = real_replay(fx, ci, **kw2)
        b = real_replay(loaded, ci, **kw2)
        assert repr(a) == repr(b), (kind, k)
        compared += 1
    assert compared >= 40 and skipped == 1


# ═════════════════════════════════════════════════════════════════════════════════════════════
# 3. rule (c) against the shadow's own harness
# ═════════════════════════════════════════════════════════════════════════════════════════════
def _pad(T, rows, n=X.HISTORY + 1):
    """Prepend flat bars so the climax row has 120 history rows (the walk's requirement); the climax index moves by the pad."""
    T_dates = [r["trade_date"] for r in rows]
    pad = n - (T.N_HIST + 1)
    days, d = [], T_dates[0] - timedelta(days=1)
    while len(days) < pad:
        if d.weekday() < 5:
            days.append(d)
        d -= timedelta(days=1)
    pre = [{"trade_date": dd, "open_price": 100.0, "high_price": 101.0, "low_price": 99.0, "close": 100.0, "volume": 2_000_000.0}
           for dd in reversed(days)]
    return pre + [{**r, **{k: float(r[k]) for k in ("open_price", "high_price", "low_price", "close", "volume")}} for r in rows], pad


def _our_decisions(T, post, climax_days):
    rows, pad = _pad(T, T.market(post))
    cal = [r["trade_date"].isoformat() for r in rows]
    eps = []
    for k in climax_days:
        j = pad + T.N_HIST + k
        ep = W.walk_one(rows, list(range(len(rows))), j, cal[j], cal, cal[-1], None, None)
        ep.update({"d0": cal[j], "ticker": "ZZZ", "company_key": "cik:1"})
        eps.append(ep)
    W.apply_open_rule(eps)
    return {e["d0"]: e["decision"] for e in eps}


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["second_rejected", "invalidated_then_admitted", "open_position_blocks", "rearm_after_outcome"])
async def test_rule_c_equals_the_shadow_harness(monkeypatch, case):
    T = GD.shadow_tests_module()
    env = T.Env(monkeypatch)
    if case == "second_rejected":
        T.TestArmDecision._two_climaxes(env, (156, 165, 150, 158))
        nights, extra = range(0, 7), [1]
    elif case == "invalidated_then_admitted":
        T.TestArmDecision._two_climaxes(env, (150, 170, 141, 165))
        nights, extra = range(0, 7), [1]
    elif case == "open_position_blocks":
        env.load("ZZZ", T.TRIGGER_THEN_TIME_STOP)
        env.cands.append({"ticker": "ZZZ", "scan_date": T.D[2], "market_cap": 1_000_000_000, "cap_tier": "small", "excluded_reason": None})
        nights, extra = range(0, 3), [2]
    else:
        env.load("ZZZ", [(150, 152, 141, 148), (150, 153, 142, 149), (150, 154, 143, 150), (150, 150, 140, 145)])
        env.cands.append({"ticker": "ZZZ", "scan_date": T.D[3], "market_cap": 1_000_000_000, "cap_tier": "small", "excluded_reason": None})
        nights, extra = range(0, 4), [3]
    for k in nights:
        await env.night(k)
    if case == "rearm_after_outcome":
        await env.night(3)
    shadow = {}
    for k in [0] + extra:
        a = env.row("ZZZ", "arm", T.D[k])
        shadow[k] = "admitted" if a["status"] == "armed" else a["reason"]
    post = env.bars["ZZZ"][T.N_HIST + 1:]
    post = [(b["open_price"], b["high_price"], b["low_price"], b["close"]) for b in post]
    ours = _our_decisions(T, post, [0] + extra)
    assert list(ours.values()) == [shadow[k] for k in [0] + extra], (case, ours, shadow)


# ═════════════════════════════════════════════════════════════════════════════════════════════
# 4. the pulls through a fake transport
# ═════════════════════════════════════════════════════════════════════════════════════════════
def _paths(tmp_path, **kw):
    return X.Paths(data=str(tmp_path / "data"), out=str(tmp_path / "out"), here=str(tmp_path / "here"), **kw)


def test_reference_pull_follows_next_url_for_both_pulls(tmp_path, monkeypatch):
    monkeypatch.setenv("POLYGON_API_KEY", "K")
    P = _paths(tmp_path)
    routes = {"active=true": (200, {"results": [{"ticker": "AAA", "active": True}], "next_url": "https://api.polygon.io/v3/x?cursor=c1"}),
              "cursor=c1": (200, {"results": [{"ticker": "BBB", "active": True}]}),
              "active=false": (200, {"results": [{"ticker": "OLD", "active": False, "delisted_utc": "2020-01-02T00:00:00Z"}]})}
    tr = PL.FakeTransport(routes)
    st = PL.pull_reference(P, tr, say=lambda *_: None)
    assert st == {"active": 2, "delisted": 1, "pages": 3}
    assert all("apiKey=K" in u for u in tr.urls) and all("limit=1000" in u or "cursor" in u for u in tr.urls)
    recs = [json.loads(ln) for ln in gzip.open(P.polygon_reference, "rt")]
    assert [(r["ticker"], r["_pull"]) for r in recs] == [("AAA", "active"), ("BBB", "active"), ("OLD", "delisted")]
    with pytest.raises(PL.PullStop):                                # made once
        PL.pull_reference(P, tr, say=lambda *_: None)


def test_reference_pull_stops_on_a_failed_page(tmp_path, monkeypatch):
    monkeypatch.setenv("POLYGON_API_KEY", "K")
    P = _paths(tmp_path)
    with pytest.raises(PL.PullStop):
        PL.pull_reference(P, PL.FakeTransport({"active=true": (500, None)}), say=lambda *_: None)
    assert not os.path.exists(P.polygon_reference)


def test_edgar_pull_reads_older_files_keeps_only_the_tags_and_records_a_404(tmp_path):
    P = _paths(tmp_path)
    os.makedirs(P.out)
    with open(P.candidate_ciks, "w") as fh:
        fh.write("# c\n1\n0000000002\n")
    sub = {"name": "Alpha Corp", "tickers": ["AAA"], "filings": {"recent": {"form": ["10-Q"], "filingDate": ["2018-02-01"],
                                                                           "accessionNumber": ["A1"], "items": [""]},
                                                                "files": [{"name": "CIK0000000001-submissions-001.json"}]}}
    older = {"form": ["10-K"], "filingDate": ["2017-03-01"], "accessionNumber": ["A0"], "items": [""]}
    facts = {"entityName": "Alpha", "facts": {"dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": [
        {"accn": "A1", "end": "2018-01-25", "val": 100, "filed": "2018-02-01", "form": "10-Q"}]}}},
        "us-gaap": {"NetIncomeLoss": {"units": {"USD": [{"accn": "A1", "start": "2017-10-01", "end": "2017-12-31", "val": 5, "filed": "2018-02-01"}]}},
                    "Revenues": {"units": {"USD": [{"val": 1}]}}}}}
    tr = PL.FakeTransport({"submissions/CIK0000000001.json": (200, sub), "CIK0000000001-submissions-001.json": (200, older),
                           "companyfacts/CIK0000000001.json": (200, facts)})
    st = PL.pull_edgar(P, tr, say=lambda *_: None)
    assert st["submissions_ok"] == 1 and st["submissions_fail"] == 1 and st["older_files"] == 1 and st["facts_ok"] == 1
    s = FT.load_submissions(P.edgar_submissions)
    assert s["0000000002"]["status"] == 404 and [f["accessionNumber"] for f in s["0000000001"]["filings"]] == ["A1", "A0"]
    f = FT.load_facts(P.xbrl_facts)
    assert set(f["0000000001"]["facts"]) == {"dei:EntityCommonStockSharesOutstanding", "us-gaap:NetIncomeLoss"}
    n = tr.n
    PL.pull_edgar(P, tr, say=lambda *_: None)                     # resume: everything recorded is skipped
    assert tr.n == n


INSTANCE_XML = b"""<?xml version="1.0" encoding="utf-8"?>
<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance" xmlns:dei="http://xbrl.sec.gov/dei/2023" xmlns:us-gaap="http://fasb.org/us-gaap/2023"
  xmlns:xbrldi="http://xbrl.org/2006/xbrldi">
  <xbrli:context id="c0"><xbrli:entity><xbrli:identifier scheme="x">1</xbrli:identifier></xbrli:entity>
    <xbrli:period><xbrli:instant>2017-12-31</xbrli:instant></xbrli:period></xbrli:context>
  <xbrli:context id="w1"><xbrli:entity><xbrli:identifier scheme="x">1</xbrli:identifier><xbrli:segment>
    <xbrldi:explicitMember dimension="us-gaap:ClassOfWarrantOrRightAxis">aaa:SeriesAMember</xbrldi:explicitMember></xbrli:segment></xbrli:entity>
    <xbrli:period><xbrli:instant>2017-12-31</xbrli:instant></xbrli:period></xbrli:context>
  <xbrli:context id="w2"><xbrli:entity><xbrli:identifier scheme="x">1</xbrli:identifier><xbrli:segment>
    <xbrldi:explicitMember dimension="us-gaap:ClassOfWarrantOrRightAxis">aaa:SeriesBMember</xbrldi:explicitMember></xbrli:segment></xbrli:entity>
    <xbrli:period><xbrli:instant>2017-12-31</xbrli:instant></xbrli:period></xbrli:context>
  <dei:DocumentPeriodEndDate contextRef="c0">2017-12-31</dei:DocumentPeriodEndDate>
  <us-gaap:ClassOfWarrantOrRightOutstanding contextRef="w1" unitRef="shares" decimals="0">30000000</us-gaap:ClassOfWarrantOrRightOutstanding>
  <us-gaap:ClassOfWarrantOrRightExercisePriceOfWarrantsOrRights1 contextRef="w1" unitRef="usd" decimals="2">20.00</us-gaap:ClassOfWarrantOrRightExercisePriceOfWarrantsOrRights1>
  <us-gaap:ClassOfWarrantOrRightOutstanding contextRef="w2" unitRef="shares" decimals="0">5000000</us-gaap:ClassOfWarrantOrRightOutstanding>
  <us-gaap:ClassOfWarrantOrRightExercisePriceOfWarrantsOrRights1 contextRef="w2" unitRef="usd" decimals="2">5.00</us-gaap:ClassOfWarrantOrRightExercisePriceOfWarrantsOrRights1>
  <us-gaap:ClassOfWarrantOrRightTitleOfSecurityWarrantsOrRightsOutstanding contextRef="c0">Warrants</us-gaap:ClassOfWarrantOrRightTitleOfSecurityWarrantsOrRightsOutstanding>
</xbrli:xbrl>"""


def test_instances_pull_picks_the_instance_and_parses_contexts_and_facts(tmp_path):
    P = _paths(tmp_path)
    os.makedirs(P.out)
    X.write_tsv(P.filings_wanted, ["cik", "accn", "primaryDocument", "form", "filingDate"],
                [{"cik": "0000000001", "accn": "0000000001-18-000001", "primaryDocument": "aaa.htm", "form": "10-Q", "filingDate": "2018-02-01"},
                 {"cik": "0000000003", "accn": "0000000003-18-000001", "primaryDocument": "c.htm", "form": "10-Q", "filingDate": "2018-02-01"}])
    idx = {"directory": {"item": [{"name": "aaa-20171231_cal.xml"}, {"name": "aaa-20171231_htm.xml"}, {"name": "FilingSummary.xml"}]}}
    tr = PL.FakeTransport({"/1/000000000118000001/index.json": (200, idx), "/1/000000000118000001/aaa-20171231_htm.xml": (200, INSTANCE_XML)})
    st = PL.pull_instances(P, tr, say=lambda *_: None)
    assert st["ok"] == 1 and st["no_index"] == 1
    inst = FT.load_instances(P.xbrl_instances)
    r = inst[("0000000001", "0000000001-18-000001")]
    assert r["status"] == 200 and r["period_end"] == "2017-12-31" and r["instance_name"] == "aaa-20171231_htm.xml"
    assert len(r["facts"]) == 5 and r["text_tags_present"] == [FT.WARRANT_TEXT]
    assert r["contexts"]["w1"]["dims"] == [["us-gaap:ClassOfWarrantOrRightAxis", "aaa:SeriesAMember"]]
    assert inst[("0000000003", "0000000003-18-000001")]["status"] == 404
    assert PL.pick_instance({"directory": {"item": [{"name": "abc-20161231.xml"}, {"name": "abc-20161231_lab.xml"}]}}, "") == "abc-20161231.xml"


def test_news_pull_marks_a_third_page_with_next_url_truncated(tmp_path, monkeypatch):
    monkeypatch.setenv("POLYGON_API_KEY", "K")
    P = _paths(tmp_path)
    os.makedirs(P.out)
    X.write_tsv(P.news_wanted, ["ticker", "d0", "kind", "gte", "lte"],
                [{"ticker": "AAA", "d0": "2019-01-02", "kind": "read3", "gte": "2018-12-27T21:00:00Z", "lte": "2018-12-31T21:00:00Z"},
                 {"ticker": "BBB", "d0": "2019-01-02", "kind": "mna", "gte": "2018-12-03T05:00:00Z", "lte": "2019-01-02T21:00:00Z"}])
    item = {"title": "t", "description": "d", "published_utc": "2018-12-28T12:00:00Z", "tickers": ["AAA"], "insights": [{"ticker": "AAA"}],
            "publisher": {"name": "P"}}
    tr = PL.FakeTransport({"ticker=AAA": (200, {"results": [item], "next_url": "https://api.polygon.io/v2/reference/news?cursor=p2"}),
                           "cursor=p2": (200, {"results": [item], "next_url": "https://api.polygon.io/v2/reference/news?cursor=p3"}),
                           "cursor=p3": (200, {"results": [item], "next_url": "https://api.polygon.io/v2/reference/news?cursor=p4"}),
                           "ticker=BBB": (200, {"results": []})})
    st = PL.pull_news(P, tr, say=lambda *_: None)
    assert st["truncated"] == 1 and st["pages"] == 4 and not any("cursor=p4" in u for u in tr.urls)
    n = FT.load_news(P.polygon_news)
    a = n[("AAA", "2019-01-02", "read3")]
    assert a["pages"] == 3 and a["truncated"] is True and len(a["items"]) == 3 and a["items"][0]["publisher"] == "P"
    assert FT.news_present(a, "AAA")["news_group"] == "unknown"                       # truncated = unknown, never present / absent
    assert FT.news_present(n[("BBB", "2019-01-02", "mna")], "BBB")["news_group"] == "absent"
    assert "published_utc.gte=2018-12-27T21%3A00%3A00Z" in tr.urls[0] and "order=desc" in tr.urls[0] and "sort=published_utc" in tr.urls[0]


def test_alpaca_ca_pull_and_the_dry_run_make_no_network_call(tmp_path, monkeypatch):
    monkeypatch.setenv("ALPACA_PAPER_API_KEY", "a")
    monkeypatch.setenv("ALPACA_PAPER_SECRET_KEY", "b")
    P = _paths(tmp_path)
    os.makedirs(P.out)
    X.write_tsv(P.suspects_wanted, ["ticker", "gap_date"], [{"ticker": "OPLN", "gap_date": "2019-06-28"}])
    tr = PL.FakeTransport({PL.ALPACA_CA: (200, {"corporate_actions": {"spin_offs": [{"ex_date": "2019-06-28"}]}})})
    assert PL.pull_alpaca_ca(P, tr, say=lambda *_: None)["ok"] == 1
    assert "start=2019-06-21" in tr.urls[0] and "end=2019-07-01" in tr.urls[0]
    lines = []
    for st in PL.STAGES:
        assert PL.main(["--" + st.replace("_", "-"), "--dry-run"], transport=PL.NoNetwork(), paths=P, say=lines.append) == 0
    assert sum(1 for ln in lines if ln == "DRY RUN COMPLETE") == len(PL.STAGES)
    with pytest.raises(PL.PullStop):
        PL.NoNetwork().get("http://x")


# ═════════════════════════════════════════════════════════════════════════════════════════════
# 5. units and the runner rules
# ═════════════════════════════════════════════════════════════════════════════════════════════
def test_the_name_cross_check_accepts_a_former_sec_name_and_lists_a_real_disagreement():
    ref = {"SQ": [{"ticker": "SQ", "_cik": "0000000001", "name": "Square, Inc. Class A Common Stock", "_pull": "delisted", "_delisted": "2025-01-21"}],
           "ZZ": [{"ticker": "ZZ", "_cik": "0000000002", "name": "Zeta Holdings", "_pull": "active", "_delisted": ""}]}
    subs = {"0000000001": {"status": 200, "name": "Block, Inc.", "formerNames": [{"name": "Square, Inc.", "from": "2009", "to": "2021"}]},
            "0000000002": {"status": 200, "name": "Totally Different Corp", "formerNames": []}}
    ids, lst = ST.name_mismatches(ref, {}, subs)
    assert ids == {PP.id_of(ref["ZZ"][0])} and len(lst) == 1


def test_numpy_scalars_leave_by_indexing_and_a_length_two_array_is_an_error():
    assert X.num(np.array([1.5])) == 1.5 and X.num(np.float64(2.0)) == 2.0
    with pytest.raises(ValueError):
        X.num(np.array([1.0, 2.0]))


def test_record_identity_is_content_based_never_id():
    a = {"ticker": "T", "_pull": "active", "_delisted": "", "_cik": "0000000001", "composite_figi": "F"}
    assert PP.id_of(a) == PP.id_of(dict(a)) and PP.id_of(a) != PP.id_of({**a, "_cik": "0000000002"})
    # source-pin-ok: a population guard over every module — no cache may key on id() of an object (the 10-24 crash class); a behaviour test can only cover the call sites it happens to reach
    import ast
    for f in ("ps_population.py", "ps_stages.py", "ps_features.py", "ps_walk.py", "ps_replay.py", "ps_goldens.py"):
        calls = [n for n in ast.walk(ast.parse((BUILD / f).read_text())) if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "id"]
        assert not calls, f                                            # no cache keyed by id() of an object it does not hold


def test_company_counts_read_the_key_literally():
    ref = {"A": [{"ticker": "A", "_cik": ""}, {"ticker": "A", "_cik": ""}],
           "B": [{"ticker": "B", "_cik": "0000000001"}, {"ticker": "B", "_cik": ""}],
           "C": [{"ticker": "C", "_cik": "0000000001"}, {"ticker": "C", "_cik": "0000000001", "composite_figi": "Z"}]}
    assert PP.company_counts(ref) == {"A": 1, "B": 2, "C": 1}


def test_owner_B_date_rule_tie_and_active():
    recs = [{"ticker": "X", "_pull": "delisted", "_delisted": "2022-05-01", "_cik": "1"},
            {"ticker": "X", "_pull": "delisted", "_delisted": "2023-01-10", "_cik": "2"},
            {"ticker": "X", "_pull": "active", "active": True, "_delisted": "", "_cik": "3"}]
    assert PP.owner_B(recs, "2022-04-01")[0]["_cik"] == "1"
    assert PP.owner_B(recs, "2022-05-01")[0]["_cik"] == "1"           # delisted on D0 still owns D0
    assert PP.owner_B(recs, "2022-06-01")[0]["_cik"] == "2"
    assert PP.owner_B(recs, "2024-01-01") == (recs[2], "active")
    tie = recs[:2] + [{"ticker": "X", "_pull": "delisted", "_delisted": "2023-01-10", "_cik": "9"}]
    assert PP.owner_B(tie, "2022-06-01") == (None, "two_delisted_same_date")


def test_gone_needs_a_key_and_a_known_date():
    act = {"0000000009", "FIGI9"}
    assert PP.gone_flag({"_delisted": "2020-01-01", "_cik": "0000000001"}, act) == "yes"
    assert PP.gone_flag({"_delisted": "2020-01-01", "_cik": "0000000009"}, act) == "no"          # a rename
    assert PP.gone_flag({"_delisted": "2020-01-01", "_cik": ""}, act) == "unknown"               # empty key: never gone
    assert PP.gone_flag({"_delisted": "", "_cik": "1", "_date_unknown": True}, act) == "unknown"
    assert PP.gone_flag({"_delisted": "", "_cik": "1"}, act) == "no"                              # active owner


def _flat_era(tmp_path, series: dict, era="B", cal=None):
    """A tiny era from {ticker: [(date, o, h, l, c, v)]} on `cal` (SPY on every date)."""
    d = tmp_path / f"era_{era}"
    d.mkdir(exist_ok=True)
    exp = d / "daily_closes_all.csv.gz"
    with gzip.open(exp, "wt") as fh:
        for x in cal:
            fh.write(f"SPY,{x},100,100,100,100,1000000\n")
        for t, rows in series.items():
            for r in rows:
                fh.write(f"{t},{r[0]},{r[1]},{r[2]},{r[3]},{r[4]},{r[5]}\n")
    spl = d / "splits.psv"
    spl.write_text("")
    P = X.Paths(data=str(d), out=str(d / "out"), here=str(d), export_B=str(exp), splits_B=str(spl))
    return PP.load_era(P, "B"), P


def test_earlier_issuer_rule_excludes_a_window_reaching_the_previous_company(tmp_path):
    cal = GD.bdays(date(2022, 1, 3), 400)
    cal = [x.isoformat() for x in cal]
    rows = [(x, 10, 10.1, 9.9, 10, 1e6) for x in cal]
    e, _P = _flat_era(tmp_path, {"INBX": rows}, cal=cal)
    switch = cal[200]
    ref = {"INBX": [{"ticker": "INBX", "_pull": "delisted", "_delisted": switch, "_cik": "0000000001", "type": "CS", "name": "Old"},
                    {"ticker": "INBX", "_pull": "active", "active": True, "_delisted": "", "_cik": "0000000002", "type": "CS", "name": "New"}]}
    ctx = PP.Ctx(ref=ref, active_keys={"0000000002"})
    nt = PP.night_table(e, ctx)
    i_after = e.bar_index("INBX", cal[201])
    i_late = e.bar_index("INBX", cal[201 + X.HISTORY])
    i_before = e.bar_index("INBX", cal[150])
    assert nt.flags[i_after] & PP.F_ID_EARLIER                         # the window reaches the old company's bars
    assert not nt.flags[i_late] & PP.F_ID_EARLIER                      # 120 sessions later the window is clean
    assert nt.rec_of(i_before)["_cik"] == "0000000001" and not nt.flags[i_before] & PP.F_ID_EARLIER
    assert nt.gone[i_before] == PP.G_YES and nt.gone[i_late] == PP.G_NO


def test_placeholder_owners_are_reresolved_and_original_symbols_never_are(tmp_path):
    cal = [x.isoformat() for x in GD.bdays(date(2021, 1, 4), 200)]
    rows = [(x, 10, 10.1, 9.9, 10, 1e6) for x in cal]
    e, _P = _flat_era(tmp_path, {"BBBY": rows, "VIAC": rows, "ORIG": rows}, cal=cal)
    e.name = "A"                                                       # the era-A owner branch on a small tree
    ref = {"BBBY": [{"ticker": "BBBY", "_pull": "delisted", "_delisted": "2023-05-03", "_cik": "0000886158", "type": "CS", "name": "Bed Bath"}],
           "ORIG": [{"ticker": "ORIG", "_pull": "active", "active": True, "_delisted": "", "_cik": "", "type": "CS", "name": "Orig"},
                    {"ticker": "ORIG", "_pull": "delisted", "_delisted": "2024-01-02", "_cik": "0000000005", "type": "CS", "name": "Other"}]}
    refetch = {"BBBY": PP.refetch_record_as_ref({"ticker": "BBBY", "name": "Bed Bath", "type": "CS", "cik": "0000886158",
                                                 "composite_figi": "F", "share_class_figi": "S", "delisted": "2022-06-30"}),
               "VIAC": PP.refetch_record_as_ref({"ticker": "VIAC", "name": "", "type": "", "cik": "", "composite_figi": "",
                                                 "share_class_figi": "", "delisted": "2022-06-30"})}
    ctx = PP.Ctx(ref=ref, refetch=refetch, refetched={"BBBY", "VIAC"}, active_keys=set())
    nt = PP.night_table(e, ctx)
    ib, iv, io = (e.bar_index(s, cal[150]) for s in ("BBBY", "VIAC", "ORIG"))
    assert PP.PATHS[nt.path[ib]] == "reresolved_delisted" and nt.rec_of(ib)["_delisted"] == "2023-05-03" and nt.gone[ib] == PP.G_YES
    assert PP.PATHS[nt.path[iv]] == "unresolved" and nt.gone[iv] == PP.G_UNKNOWN and nt.tcode[iv] == PP.T_UNKNOWN
    assert PP.TSRC[nt.tsrc[iv]] == "record_without_type"               # never the fallback table (R38)
    assert PP.PATHS[nt.path[io]] == "active" and nt.gone[io] == PP.G_NO and nt.key_of(io) == "sym:ORIG"     # R61
    assert not any(PP.owner_has_placeholder(nt.recs[o]) for o in set(nt.owner[nt.owner >= 0].tolist()))


def test_superset_prefilter_never_drops_a_detector_climax(tmp_path):
    rng = np.random.default_rng(7)
    cal = [x.isoformat() for x in GD.bdays(date(2021, 1, 4), 400)]
    series = {}
    for k in range(6):
        rows, _ = GD.detector_series("climax")
        base = [(cal[i], 10, 10.2, 9.8, 10, 1e6) for i in range(150)]
        c = 10.0
        out = list(base)
        for i in range(150, 400):
            g = rng.normal(0.02 if (i // 37) % 3 == 0 else -0.005, 0.06)
            o = c * (1 + rng.normal(0.015, 0.02))
            c2 = max(0.5, c * (1 + g))
            out.append((cal[i], o, max(o, c2) * 1.02, min(o, c2) * 0.98, c2, 1e6 * (1 + i % 23)))
            c = c2
        series["R" + "ABCDEF"[k]] = out
    e, _P = _flat_era(tmp_path, series, cal=cal)
    e.detect = np.ones(len(e.D.c), bool)
    sup = PP.superset_mask(e)
    hits = 0
    for t, s in enumerate(e.tickers):
        if s == "SPY":
            continue
        a, b = e.rows_of(t)
        dicts = PP.ticker_dicts(e, t)
        for j in range(X.HISTORY - 1, b - a):
            for cap in (None, 20_000_000_000, 1):
                if pdm.compute_parabolic_metrics(dicts[j - 119: j + 1], market_cap=cap)["stage"] == "climax" and e.band[a + j]:
                    hits += 1
                    assert sup[a + j], (s, j, cap)
    assert hits > 0


def test_cap_and_the_share_basis_on_era_B_splits():
    b = FT.Basis("B", splits={"T": [(date(2023, 6, 1), 2.0)]})
    assert b.S("T", "2023-03-31", "2023-07-01") == 2.0 and b.S("T", "2023-06-01", "2023-07-01") == 1.0
    sub = {"status": 200, "filings": [{"form": "10-Q", "filingDate": "2023-05-10", "accessionNumber": "A1"},
                                      {"form": "10-Q/A", "filingDate": "2023-06-20", "accessionNumber": "A2"},
                                      {"form": "10-Q", "filingDate": "2023-08-10", "accessionNumber": "A3"}]}
    facts = {"status": 200, "facts": {"dei:EntityCommonStockSharesOutstanding": [{"accn": "A1", "end": "2023-05-01", "val": 1000}]}}
    c = FT.cap_for("T", "2023-07-03", "1", sub, facts, b, 10.0)
    assert c["cap"] == 1000 * 2.0 * 10.0 and c["filing_accn"] == "A1"            # the amendment is not the periodic report (R15)
    assert FT.cap_for("T", "2023-07-03", "1", sub, facts, b, 10.0, index=FT.FilingIndex(sub)) == c
    b2 = FT.Basis("B", splits={"T": [(date(2023, 5, 5), 2.0)]})                    # a split between `end` and `filed`
    assert FT.cap_for("T", "2023-07-03", "1", sub, facts, b2, 10.0)["cap_reason"] == "split_between_end_and_filed"
    two = {"status": 200, "facts": {"dei:EntityCommonStockSharesOutstanding": [{"accn": "A1", "end": "2023-05-01", "val": 1000},
                                                                                {"accn": "A1", "end": "2023-05-01", "val": 50}]}}
    assert FT.cap_for("T", "2023-07-03", "1", sub, two, b, 10.0)["cap_reason"] == "multi_class"


def test_dilution_reads_the_balance_sheet_tranches_not_the_cover_date():
    """R39 regression: the cover fact's `end` (2018-01-25) is not the balance-sheet date (2017-12-31); the tranches must still be read."""
    inst = PL.parse_instance(INSTANCE_XML)
    inst["status"] = 200
    sub = {"status": 200, "filings": [{"form": "10-Q", "filingDate": "2018-02-01", "accessionNumber": "A1", "reportDate": "2017-12-31"}]}
    b = FT.Basis("B", splits={})
    capd = {"cap": 1e9, "cap_reason": "", "filing_accn": "A1", "shares_d0": 100_000_000.0, "fact_end": "2018-01-25"}
    out = FT.dilution_feature("T", "2018-03-01", "1", sub, None, {("1", "A1"): inst}, b, 25.0, 8.0, capd)
    assert out["tranche_count"] == 2
    assert out["dilution_ratio"] == pytest.approx(0.30)               # $20 in (8, 25]: newly unlocked; $5 was already in the money
    assert out["dilution_ratio_itm"] == pytest.approx(0.35) and out["dilution_bucket"] == "ge20" and out["warrant_text_present"] == 1
    unpaired = dict(inst, facts=[f for f in inst["facts"] if not (f["context"] == "w2" and "ExercisePrice" in f["tag"])])
    assert FT.dilution_feature("T", "2018-03-01", "1", sub, None, {("1", "A1"): unpaired}, b, 25.0, 8.0, capd)["dilution_reason"] == "unpaired_tranche"
    failed = {("1", "A1"): {"status": 595}}
    assert FT.dilution_feature("T", "2018-03-01", "1", sub, None, failed, b, 25.0, 8.0, capd)["dilution_bucket"] == "unknown"


def test_eight_k_charging_and_the_earnings_exit_window():
    cal = ["2023-05-01", "2023-05-02", "2023-05-03", "2023-05-04", "2023-05-05", "2023-05-08"]
    sub = {"status": 200, "filings": [{"form": "8-K", "items": "2.02,9.01", "acceptanceDateTime": "2023-05-02T20:30:00.000Z"},   # 16:30 ET
                                      {"form": "8-K", "items": "2.02", "acceptanceDateTime": "2023-05-05T21:00:00.000Z"}]}         # Fri 17:00 ET
    k = FT.eight_k_feature(sub, "1", "2023-05-03", cal, ["2023-05-04", "2023-05-05"])
    assert k["earnings_flag"] == "on_climax_day"                       # after 16:00 on 05-02 -> charged to 05-03 = D0
    assert k["earnings_after"] == ["2023-05-05"]                       # after Friday's close, before Monday's open
    assert FT.eight_k_feature(sub, "1", "2023-05-08", cal, [])["earnings_flag"] == "on_climax_day"     # Fri 17:00 ET -> Monday = D0
    assert FT.eight_k_feature(sub, "1", "2023-05-05", cal, [])["earnings_flag"] == "none"              # charged 05-03 and 05-08: neither
    assert FT.eight_k_feature({"status": 200, "filings": [{"form": "6-K"}, {"form": "20-F"}]}, "1", "2023-05-03", cal, [])["earnings_flag"] == "unknown"


def test_news_window_is_et_close_bounded_utc_timestamps():
    cal = ["2023-03-08", "2023-03-09", "2023-03-10", "2023-03-13", "2023-03-14"]
    gte, lte, start = FT.news_window_read3(cal, "2023-03-10")
    assert start == "2023-03-13" and gte == "2023-03-08T21:00:00Z" and lte == "2023-03-13T20:00:00Z"   # EST then EDT (DST on 03-12)
    assert FT.news_window_read3(cal, None) is None


def test_swing_quarters_and_the_derived_q4():
    facts = {"status": 200, "facts": {"us-gaap:NetIncomeLoss": [
        {"unit": "USD", "start": "2022-01-01", "end": "2022-09-30", "val": -30, "filed": "2022-11-05"},
        {"unit": "USD", "start": "2022-01-01", "end": "2022-12-31", "val": -10, "filed": "2023-03-01"},
        {"unit": "USD", "start": "2022-07-01", "end": "2022-09-30", "val": -8, "filed": "2022-11-05"},
        {"unit": "USD", "start": "2023-01-01", "end": "2023-03-31", "val": 4, "filed": "2023-05-05"}]}}
    q = FT.quarters_before(facts, "2023-06-01")
    assert [(e, v) for e, v, _ in q] == [("2022-09-30", -8), ("2022-12-31", 20), ("2023-03-31", 4)]
    assert FT.swing_feature(facts, "1", "2023-06-01", "2023-04-01")["swing_group"] == "no_swing"   # Q4 +20 then +4: no swing
    f2 = {"status": 200, "facts": {"us-gaap:NetIncomeLoss": facts["facts"]["us-gaap:NetIncomeLoss"][2:3] + [
        {"unit": "USD", "start": "2022-10-01", "end": "2022-12-31", "val": 5, "filed": "2023-02-20"}]}}
    sw = FT.swing_feature(f2, "1", "2023-03-01", "2023-02-01")
    assert sw["swing_group"] == "swing" and sw["swing_group_any"] == "swing"
    assert FT.swing_feature(f2, "1", "2023-03-01", "2023-02-21")["swing_group"] == "no_swing"   # filed before the run's base


def test_rule_c_releases_a_degraded_episode_at_its_last_walked_bar():
    eps = [{"d0": "2023-01-02", "ticker": "A", "company_key": "k", "r5_status": "degraded", "last_walked_date": "2023-01-04"},
           {"d0": "2023-01-04", "ticker": "A", "company_key": "k", "r5_status": "settled", "r5_exit_date": "2023-01-09"},
           {"d0": "2023-01-05", "ticker": "B", "company_key": "k", "r5_status": "settled", "r5_exit_date": "2023-01-09"},
           {"d0": "2023-01-09", "ticker": "A", "company_key": "k", "r5_status": "settled", "r5_exit_date": "2023-01-12"}]
    t = W.apply_open_rule(eps)
    assert [e["decision"] for e in eps] == ["admitted", "admitted", "episode_already_open", "admitted"]
    assert t == {"admitted": 3, "episode_already_open": 1}


def test_ended_mid_walk_is_booked_at_the_last_close_with_the_adverse_haircut():
    T = GD.shadow_tests_module()
    dmap = GD.redate_map(T)
    rows, ci, kw = GD.golden_rows(T, dmap, pad_to=X.HISTORY)
    cut = rows[: ci + 3]                                               # the series ends 2 sessions into the walk (a delisting)
    cal = [r["trade_date"].isoformat() for r in rows]
    ep = W.walk_one(cut, list(range(len(cut))), ci, cal[ci], cal, cal[-1], None, None)
    assert ep["r5_status"] == "ended_mid_walk" and ep["stop_reason"] == "end_of_series"
    entry, risk, last = 140.0, ep["r5_risk"], cut[-1]["close"]
    assert ep["r5_r_last_close"] == pytest.approx((entry - last) / risk)
    assert ep["r5_ended_class"] in ("other", "collapse", "pinned")
    assert ep["last_walked_date"] == cal[ci + 2]


def test_tail_clause_is_never_vacuous_and_needs_three_companies():
    S = [{"r5_r": 3.5, "company_key": "a", "r5_entry_month": "2023-01", "r5_pnl_adr": 1.0},
         {"r5_r": 3.1, "company_key": "a", "r5_entry_month": "2023-02", "r5_pnl_adr": 1.0},
         {"r5_r": 4.0, "company_key": "b", "r5_entry_month": "2023-03", "r5_pnl_adr": 1.0}]
    assert W.tail_clause(S)["pass"] is False and W.tail_clause([])["pass"] is False
    S.append({"r5_r": 3.0, "company_key": "c", "r5_entry_month": "2023-04", "r5_pnl_adr": 1.0})
    assert W.tail_clause(S)["pass"] is True


def test_the_seal_drops_a_2025_bar_at_read_and_refuses_a_later_date(tmp_path):
    cal = [x.isoformat() for x in GD.bdays(date(2024, 12, 20), 10)]
    e, _P = _flat_era(tmp_path, {"AAA": [(x, 1, 1, 1, 1, 1) for x in cal]}, cal=cal)
    assert max(e.cal) <= X.CUT_B and e.info["dated_after_cut"] > 0
    with pytest.raises(X.GuardStop):
        X.seal_date("2025-01-02")


def test_the_patched_constant_refuses_in_the_wrong_process():
    code = ("import sys; sys.path.insert(0, %r); import ps_population as PP\n"
            "try:\n    PP.assert_dollar_vol_const('P2')\nexcept PP.GuardStop:\n    sys.exit(7)\nsys.exit(0)") % str(BUILD)
    assert subprocess.run([sys.executable, "-c", code], cwd=str(REPO)).returncode == 7     # a P2 process that finds 10,000,000
    code2 = ("import sys; sys.path.insert(0, %r); import ps_population as PP\nPP.patch_p2_constant()\n"
             "try:\n    PP.assert_dollar_vol_const('P1')\nexcept PP.GuardStop:\n    sys.exit(7)\nsys.exit(0)") % str(BUILD)
    assert subprocess.run([sys.executable, "-c", code2], cwd=str(REPO)).returncode == 7    # a P1 process that finds anything else
    # source-pin-ok: proves the live detector file is untouched — the P2 constant patch must exist only at runtime, and no behaviour of the replay process can show the file on disk unchanged
    on_disk = (REPO / "agents" / "market_intelligence" / "parabolic_detector.py").read_text()
    assert "_MIN_DOLLAR_VOL_TODAY  = 10_000_000" in on_disk                                 # the patch exists only at runtime


def test_bootstrap_constants_are_the_registered_ones():
    assert (X.BOOT_DRAWS, X.BOOT_SEED) == (2000, 702)
    d, lo, hi, red = W.diff_ci([1.0] * 5, ["2023-01"] * 5, [0.0] * 5, ["2023-02"] * 5, "k")
    assert d == 1.0 and red > 0                                        # two months, one per group: half the draws leave a group empty


# ═════════════════════════════════════════════════════════════════════════════════════════════
# 6 + 7. the synthetic tree: every gate, then the end-to-end run
# ═════════════════════════════════════════════════════════════════════════════════════════════
# ═════════════════════════════════════════════════════════════════════════════════════════════
# 5b. the review fixes (10-28)
# ═════════════════════════════════════════════════════════════════════════════════════════════
def _cent_split_series(n=60, split_at=40, ratio=4.0):
    """A forward-split name on Alpaca's layout: the adjusted close is the raw close moved to the post-split basis and ROUNDED TO CENTS,
    so raw / adjusted wanders around 4 by rounding alone before the split (GME's 3.9993..3.9997 on the real file)."""
    ds = [x.isoformat() for x in GD.bdays(date(2020, 6, 1), n)]
    rng = np.random.default_rng(3)
    raw = np.empty(n)
    for k in range(n):
        raw[k] = round(float(101.0 + rng.uniform(-3, 3)) * (ratio if k < split_at else 1.0), 2)
    adj = np.array([round(raw[k] / ratio, 2) if k < split_at else raw[k] for k in range(n)])
    return ds, raw / adj


def test_the_era_A_split_test_reads_a_factor_step_not_cent_rounding(tmp_path):
    ds, fac = _cent_split_series()
    b = FT.Basis("A", dates={"T": ds}, fac={"T": fac})
    pre = [(i, j) for i in range(40) for j in range(i + 1, 40)]
    noisy = [(i, j) for i, j in pre if abs(b.S("T", ds[i], ds[j]) - 1.0) > 1e-9]
    assert len(noisy) > len(pre) // 2 and max(abs(b.S("T", ds[i], ds[j]) - 1.0) for i, j in noisy) < 0.01   # the first build's `S != 1`
    assert all(b.split_between("T", ds[i], ds[j]) is False for i, j in pre)      # no split: the factor only wanders by rounding
    assert b.split_between("T", ds[30], ds[45]) is True                # the 4-for-1 executes inside (end, filed]
    assert b.split_between("T", ds[45], ds[30]) is True                # either order
    assert b.split_between("T", "2020-01-02", ds[10]) is None          # before the first bar = unknown
    sub = {"status": 200, "filings": [{"form": "10-Q", "filingDate": ds[20], "accessionNumber": "A1"}]}
    facts = {"status": 200, "facts": {"dei:EntityCommonStockSharesOutstanding": [{"accn": "A1", "end": ds[5], "val": 1000}]}}
    c = FT.cap_for("T", ds[50], "1", sub, facts, b, 100.0)
    assert c["cap_reason"] == "" and c["cap"] == pytest.approx(1000 * b.S("T", ds[5], ds[50]) * 100.0) and 3.99 < b.S("T", ds[5], ds[50]) < 4.01
    sub2 = {"status": 200, "filings": [{"form": "10-Q", "filingDate": ds[45], "accessionNumber": "A1"}]}
    facts2 = {"status": 200, "facts": {"dei:EntityCommonStockSharesOutstanding": [{"accn": "A1", "end": ds[30], "val": 1000}]}}
    assert FT.cap_for("T", ds[50], "1", sub2, facts2, b, 100.0)["cap_reason"] == "split_between_end_and_filed"
    # the arrays path (ST.EraBasis) gives the same answers
    e, _P = _flat_era(tmp_path, {"T": [(d, 10, 10, 10, 10, 1e6) for d in ds]}, cal=ds)
    e.name = "A"
    a, bb = e.rows_of(e.tid["T"])
    e.fac[a:bb] = fac
    eb = ST.EraBasis(e)
    for lo, hi in ((ds[5], ds[20]), (ds[30], ds[45]), (ds[0], ds[59]), (ds[41], ds[59])):
        assert eb.split_between("T", lo, hi) == b.split_between("T", lo, hi), (lo, hi)
    assert eb.S("T", ds[5], ds[50]) == pytest.approx(b.S("T", ds[5], ds[50]))


def test_alias_leftover_rows_take_a_delisted_record_never_the_later_holders_active_one(tmp_path):
    cal = [x.isoformat() for x in GD.bdays(date(2020, 1, 2), 200)]
    e, _P = _flat_era(tmp_path, {"XL": [(x, 10, 10.1, 9.9, 10, 1e6) for x in cal]}, cal=cal)
    e.name = "A"
    old = {"ticker": "XL", "_pull": "delisted", "_delisted": "2020-05-21", "_cik": "0000000001", "type": "CS", "name": "XL Group"}
    new = {"ticker": "XL", "_pull": "active", "active": True, "_delisted": "", "_cik": "0000000002", "type": "CS", "name": "Later holder"}
    ctx = PP.Ctx(ref={"XL": [old, new]}, alias_outside={"XL": {"outside": len(cal), "inside": 0}}, active_keys={"0000000002"})
    nt = PP.night_table(e, ctx)
    i_before, i_on, i_after = (e.bar_index("XL", d) for d in ("2020-05-20", "2020-05-21", "2020-05-22"))
    assert nt.rec_of(i_before)["name"] == "XL Group" and PP.PATHS[nt.path[i_before]] == "alias_date_rule"
    assert nt.rec_of(i_on)["name"] == "XL Group"                                  # delisted on D0 still owns D0
    assert nt.owner[i_after] == -1 and PP.PATHS[nt.path[i_after]] == "no_record_covering_d0"     # never the later holder
    assert all(nt.flags[k] & PP.F_ALIAS_OUTSIDE for k in (i_before, i_after))
    PP.assert_alias_owners(nt)                                                    # passes
    act = next(k for k, r in enumerate(nt.recs) if r is new or r.get("name") == "Later holder")
    nt.owner[i_after] = act                                                       # what the first build did
    with pytest.raises(X.GuardStop):
        PP.assert_alias_owners(nt)
    tie = PP.owner_alias([old, dict(old, _cik="0000000003")], "2020-05-01")
    assert tie == (None, "two_delisted_same_date")


def test_the_name_cross_check_strips_sec_state_tags():
    pairs = [("Bank of America Corporation", "BANK OF AMERICA CORP /DE/"), ("Qualcomm Inc", "QUALCOMM INC/DE"),
             ("Marriott International", "MARRIOTT INTERNATIONAL INC /MD/"), ("TJX Companies, Inc.", "TJX COMPANIES INC /DE/"),
             ("Valero Energy Corporation", "VALERO ENERGY CORP/TX"), ("International Paper Company", "INTERNATIONAL PAPER CO /NEW/"),
             ("Progressive Corporation", "PROGRESSIVE CORP/OH/")]
    for poly, sec in pairs:
        assert FT.name_normal(poly) == FT.name_normal(sec), (poly, sec, FT.name_normal(poly), FT.name_normal(sec))
    ref = {t: [{"ticker": t, "_cik": f"000000000{k}", "name": poly, "_pull": "active", "_delisted": ""}] for k, (t, (poly, _s)) in
           enumerate(zip(("BAC", "QCOM", "MAR", "TJX", "VLO", "IP", "PGR"), pairs))}
    subs = {f"000000000{k}": {"status": 200, "name": sec, "formerNames": []} for k, (_p, sec) in enumerate(pairs)}
    assert ST.name_mismatches(ref, {}, subs)[0] == set()
    assert FT.name_normal("Inhibrx Inc") != FT.name_normal("Inhibrx Biosciences")    # a real disagreement still disagrees


def _control_era(tmp_path, old_delisted_idx, same_company=False):
    tmp_path.mkdir(parents=True, exist_ok=True)
    cal = [x.isoformat() for x in GD.bdays(date(2023, 6, 1), 400)]
    rows = [(x, 34, 34.3, 33.7, 34, 1e6) for k, x in enumerate(cal) if k != 200]      # the one-session hole at the switch
    e, _P = _flat_era(tmp_path, {"INBX": rows}, cal=cal)
    old = {"ticker": "INBX", "_pull": "delisted", "_delisted": cal[old_delisted_idx], "_cik": "0000000011", "type": "CS", "name": "Inhibrx Inc"}
    new = {"ticker": "INBX", "_pull": "active", "active": True, "_delisted": "", "_cik": "0000000011" if same_company else "0000000012",
           "type": "CS", "name": "Inhibrx Biosciences"}
    nt = PP.night_table(e, PP.Ctx(ref={"INBX": [old, new]}, active_keys={new["_cik"]}))
    return e, nt, [old, new], cal


def test_the_earlier_issuer_control_passes_whichever_record_owns_the_control_night(tmp_path):
    # Polygon dates the old record on its last bar: the new record owns the control night, which must carry the flag
    e, nt, recs, cal = _control_era(tmp_path, 199)
    ok, lines = ST.earlier_issuer_control(e, nt, recs, "INBX", cal[201])
    assert ok and "active-owned and flagged" in lines[-1]
    # a 2-session lag: the OLD record owns the control night by the date rule (the first build refused here on a correct pipeline)
    e, nt, recs, cal = _control_era(tmp_path / "lag", 202)
    i = e.bar_index("INBX", cal[201])
    assert not nt.flags[i] & PP.F_ID_EARLIER and nt.rec_of(i)["name"] == "Inhibrx Inc"
    ok, lines = ST.earlier_issuer_control(e, nt, recs, "INBX", cal[201])
    assert ok and cal[203] in lines[-1], lines
    # the rule broken (both records one company): the control refuses in both shapes
    for idx, sub in ((199, "b1"), (202, "b2")):
        e, nt, recs, cal = _control_era(tmp_path / sub, idx, same_company=True)
        assert ST.earlier_issuer_control(e, nt, recs, "INBX", cal[201])[0] is False


def test_former_symbols_find_the_symbol_in_use_at_d0():
    fb = {"ticker": "FB", "_pull": "delisted", "_delisted": "2022-06-09", "_cik": "0001326801", "type": "CS", "composite_figi": "C1",
          "share_class_figi": "S1"}
    ref = {"META": [{"ticker": "META", "_pull": "active", "active": True, "_delisted": "", "_cik": "0001326801", "type": "CS",
                     "composite_figi": "C1", "share_class_figi": "S1"}],
           "FB": [fb],
           "FBWS": [{"ticker": "FBWS", "_pull": "delisted", "_delisted": "2021-01-04", "_cik": "0001326801", "type": "WARRANT",
                     "composite_figi": "", "share_class_figi": "W1"}],
           "VIAC": [{"ticker": "VIAC", "_pull": "delisted", "_delisted": "2022-02-16", "_cik": "0000813828", "type": "CS", "share_class_figi": "SV"}],
           "VIACA": [{"ticker": "VIACA", "_pull": "delisted", "_delisted": "2022-02-16", "_cik": "0000813828", "type": "CS", "share_class_figi": "SVA"}],
           "AA1": [{"ticker": "AA1", "_pull": "delisted", "_delisted": "2020-01-02", "_cik": "0000000077", "type": "CS"}],
           "AA2": [{"ticker": "AA2", "_pull": "delisted", "_delisted": "2020-01-02", "_cik": "0000000077", "type": "CS"}]}
    fs = PP.FormerSymbols(ref)
    assert fs.at("META", "2019-05-01", "0001326801", "C1", "S1", "CS") == ("FB", "renamed")
    assert fs.at("META", "2022-07-01", "0001326801", "C1", "S1", "CS") == ("META", "series")
    assert fs.at("META", "2020-06-01", "0001326801", "", "", "CS") == ("FB", "renamed")       # by CIK and type: the warrant never
    assert fs.at("VIACA", "2021-01-04", "0000813828", "", "SVA", "CS") == ("VIACA", "series")  # another share class is no rename
    assert fs.at("AA3", "2019-06-03", "0000000077", "", "", "CS") == ("", "ambiguous")


def test_a_reference_pull_retried_after_a_failed_page_holds_each_record_once(tmp_path, monkeypatch):
    monkeypatch.setenv("POLYGON_API_KEY", "K")
    P = _paths(tmp_path)
    good = {"active=true": (200, {"results": [{"ticker": "AAA", "active": True}, {"ticker": "ABC", "active": True}],
                                  "next_url": "https://api.polygon.io/v3/x?cursor=c1"}),
            "cursor=c1": (200, {"results": [{"ticker": "ZZZ", "active": True}]}),
            "active=false": (200, {"results": [{"ticker": "ABC", "active": False, "delisted_utc": "2023-05-01T00:00:00Z", "cik": "1"}]})}
    with pytest.raises(PL.PullStop):
        PL.pull_reference(P, PL.FakeTransport({**good, "cursor=c1": (503, None)}), say=lambda *_: None)
    assert os.path.exists(P.polygon_reference + ".partial") and not os.path.exists(P.polygon_reference)
    PL.pull_reference(P, PL.FakeTransport(good), say=lambda *_: None)
    ref = PP.load_reference(P.polygon_reference)
    assert {t: len(v) for t, v in ref.items()} == {"AAA": 1, "ABC": 2, "ZZZ": 1}   # served: 4 records, each once
    assert PP.reference_duplicates(ref) == {}
    assert PP.owner_B(ref["ABC"], "2023-04-01")[1] == "delisted_date_rule"
    doubled = {"ABC": ref["ABC"] + ref["ABC"]}
    assert PP.reference_duplicates(doubled) == {"ABC": 2}


def _edgar_paths(tmp_path, ciks):
    P = _paths(tmp_path)
    os.makedirs(P.out, exist_ok=True)
    Path(P.candidate_ciks).write_text("".join(c + "\n" for c in ciks))
    return P


def test_edgar_resume_re_requests_a_transient_failure_and_complete_needs_every_answer(tmp_path):
    P = _edgar_paths(tmp_path, ["0000000001", "0000000002"])
    sub = lambda n: {"name": n, "filings": {"recent": {"form": ["10-Q"], "filingDate": ["2018-02-01"], "accessionNumber": ["A1"], "items": [""]}}}
    ok_routes = {"submissions/CIK0000000001.json": (200, sub("One")), "companyfacts/CIK0000000001.json": (200, {"facts": {}}),
                 "submissions/CIK0000000002.json": (200, sub("Two")), "companyfacts/CIK0000000002.json": (200, {"facts": {}})}
    lines = []
    tr1 = PL.FakeTransport({**ok_routes, "submissions/CIK0000000002.json": (503, None)})
    assert PL.main(["--edgar", "--run"], transport=tr1, paths=P, say=lines.append) == 4
    assert any(ln.startswith("PULL INCOMPLETE") and "0000000002" in ln for ln in lines)
    assert any("0000000002" in q for q in RP.pull_coverage(P, "climax"))          # the climax gate refuses on it
    tr2 = PL.FakeTransport(ok_routes)
    lines = []
    assert PL.main(["--edgar", "--run"], transport=tr2, paths=P, say=lines.append) == 0 and lines[-1].startswith("PULL COMPLETE")
    assert tr2.urls == ["https://data.sec.gov/submissions/CIK0000000002.json"]    # only the transient one is re-requested
    assert FT.load_submissions(P.edgar_submissions)["0000000002"]["status"] == 200   # the loader keeps the last record
    assert RP.pull_coverage(P, "climax") == []
    assert PL.is_final(404) and PL.is_final(410) and PL.is_final(596) and not PL.is_final(403) and not PL.is_final(429)
    assert not PL.is_final(599) and not PL.is_final(598) and not PL.is_final(503)


def test_a_failed_older_submissions_file_reads_unknown_never_none(tmp_path):
    P = _edgar_paths(tmp_path, ["0000000001"])
    sub = {"name": "Alpha", "filings": {"recent": {"form": ["10-Q", "8-K"], "filingDate": ["2018-02-01", "2018-01-10"], "accessionNumber": ["A1", "E1"],
                                                   "items": ["", "2.02"], "acceptanceDateTime": ["", "2018-01-10T21:30:00.000Z"]},
                                        "files": [{"name": "CIK0000000001-submissions-001.json"}]}}
    routes = {"submissions/CIK0000000001.json": (200, sub), "CIK0000000001-submissions-001.json": (503, None),
              "companyfacts/CIK0000000001.json": (200, {"facts": {}})}
    st = PL.pull_edgar(P, PL.FakeTransport(routes), say=lambda *_: None)
    assert st["transient"] == 1
    rec = FT.load_submissions(P.edgar_submissions)["0000000001"]
    assert rec["status"] == 200 and rec["older_files_failed"] is True and rec["coverage_from"] == "2018-01-10"
    assert rec["older_files"] == [{"name": "CIK0000000001-submissions-001.json", "status": 503}]
    assert "0000000001" not in PL.existing_keys(P.edgar_submissions, PL.KEYS["edgar_submissions"])     # re-requested on resume
    b = FT.Basis("B", splits={})
    facts = {"status": 200, "facts": {"dei:EntityCommonStockSharesOutstanding": [{"accn": "A1", "end": "2018-01-25", "val": 100}]}}
    assert FT.cap_for("T", "2018-03-01", "1", rec, facts, b, 10.0)["cap_reason"] == ""            # the filing found is inside the block
    assert FT.cap_for("T", "2017-06-01", "1", rec, facts, b, 10.0)["cap_reason"] == "older_files_failed"   # never "no report before D0"
    whole = dict(rec, older_files_failed=False)
    assert FT.cap_for("T", "2017-06-01", "1", whole, facts, b, 10.0)["cap_reason"] == "no_periodic_report_before_d0"
    cal = [x.isoformat() for x in GD.bdays(date(2017, 5, 1), 300)]
    assert FT.eight_k_feature(rec, "1", "2017-06-01", cal, [])["earnings_reason"] == "older_files_failed"
    assert FT.eight_k_feature(whole, "1", "2017-06-01", cal, [])["earnings_flag"] == "none"
    assert FT.eight_k_feature(rec, "1", "2018-01-11", cal, [])["earnings_reason"] == "older_files_failed"   # D0-2 precedes the block
    assert FT.eight_k_feature(rec, "1", "2018-01-12", cal, [])["earnings_flag"] == "on_climax_day"     # the block covers this window
    assert FT.item_201_near(rec, "2017-06-01", cal) == (None, "")
    # an older file SEC answers 404 (listed, no longer served): the record is DONE (never re-requested forever) but stays holed
    lines = []
    assert PL.main(["--edgar", "--run"], transport=PL.FakeTransport({**routes, "CIK0000000001-submissions-001.json": (404, None)}), paths=P,
                   say=lines.append) == 0 and lines[-1].startswith("PULL COMPLETE")
    gone = FT.load_submissions(P.edgar_submissions)["0000000001"]
    assert gone["older_files_failed"] is True and gone["older_files"][0]["status"] == 404
    assert "0000000001" in PL.existing_keys(P.edgar_submissions, PL.KEYS["edgar_submissions"]) and RP.pull_coverage(P, "climax") == []
    assert FT.cap_for("T", "2017-06-01", "1", gone, facts, b, 10.0)["cap_reason"] == "older_files_failed"
    n = sum(1 for _ in gzip.open(P.edgar_submissions, "rt"))
    tr = PL.FakeTransport(routes)
    PL.pull_edgar(P, tr, say=lambda *_: None)
    assert tr.n == 0 and sum(1 for _ in gzip.open(P.edgar_submissions, "rt")) == n                      # done: nothing re-requested
    # a sustained SEC 403 stops the pull (resume later) and writes no record for that CIK
    Q = _edgar_paths(tmp_path / "q", ["0000000005"])
    lines = []
    assert PL.main(["--edgar", "--run"], transport=PL.FakeTransport({"submissions/CIK0000000005.json": (403, None)}), paths=Q,
                   say=lines.append) == 3 and any("rate-limiting" in ln for ln in lines)
    assert "0000000005" not in PL.latest_records(Q.edgar_submissions, PL.KEYS["edgar_submissions"])


def test_a_cut_short_pull_file_refuses_never_crashes(tmp_path):
    p = tmp_path / "x.jsonl.gz"
    with gzip.open(p, "wt") as fh:
        fh.write('{"cik": "1", "status": 200}\n{"cik": "2", "sta')
    with pytest.raises(X.GuardStop):
        FT.read_jsonl(str(p))
    raw = (tmp_path / "y.jsonl.gz")
    full = gzip.compress(b'{"cik": "1", "status": 200}\n' * 200)
    raw.write_bytes(full[: len(full) // 2])
    with pytest.raises(X.GuardStop):
        FT.read_jsonl(str(raw))
    with pytest.raises(PL.PullStop):
        PL.latest_records(str(raw), PL.KEYS["edgar_submissions"])


def test_the_last_sessions_earnings_window_closes_at_the_next_nyse_open():
    cal = ["2024-12-18", "2024-12-19", "2024-12-20", "2024-12-23", "2024-12-24", "2024-12-26", "2024-12-27", "2024-12-30", "2024-12-31"]
    walk = cal[2:]
    k8 = lambda acc: {"status": 200, "filings": [{"form": "8-K", "items": "2.02", "acceptanceDateTime": acc}]}
    assert FT.eight_k_feature(k8("2026-02-10T21:05:00.000Z"), "1", "2024-12-19", cal, walk)["earnings_after"] == []     # a sealed-period fact
    assert FT.eight_k_feature(k8("2024-12-31T21:05:00.000Z"), "1", "2024-12-19", cal, walk)["earnings_after"] == ["2024-12-31"]   # 16:05 ET
    assert FT.eight_k_feature(k8("2025-01-02T13:00:00.000Z"), "1", "2024-12-19", cal, walk)["earnings_after"] == ["2024-12-31"]   # 08:00 ET
    assert FT.eight_k_feature(k8("2025-01-02T15:00:00.000Z"), "1", "2024-12-19", cal, walk)["earnings_after"] == []     # 10:00 ET: past it
    with pytest.raises(X.GuardStop):
        FT.eight_k_feature(k8("2024-12-31T21:05:00.000Z"), "1", "2024-12-19", cal + ["2025-01-02"], walk + ["2025-01-02"])


def test_the_runner_refuses_other_paths_outside_the_tests(tmp_path, monkeypatch):
    assert RP.paths_from_json(RP.paths_to_json(X.LOCAL)) == X.LOCAL
    other = RP.paths_to_json(_paths(tmp_path))
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    for argv in (["--dry-run", "--paths-json", other], ["--print-pins", "--paths-json", other], ["--step0", "derive", "--paths-json", other],
                 ["--walk", "--paths-json", other], ["--walk-pop", "P1", "--paths-json", other], ["--detect", "P1", "--paths-json", other]):
        assert RP.main(argv) == 2, argv
    assert not os.path.exists(_paths(tmp_path).out)                   # nothing written


def _nyse(a, b):
    return X.nyse_sessions(a, b)


def _run_series(cal, d0_idx, p0, vol0, post_days=12, end_idx=None):
    """Flat at p0 then the golden's 20-session run ending at cal[d0_idx], then a decline (a short winner), then flat."""
    rows, _ = GD.detector_series("climax")
    run = rows[100:]
    scale = p0 / 10.0
    out = []
    last = len(cal) - 1 if end_idx is None else end_idx
    for i in range(0, d0_idx - 19):
        out.append((cal[i], p0, p0 * 1.02, p0 * 0.98, p0, vol0))
    for k, r in enumerate(run):
        out.append((cal[d0_idx - 19 + k], r["open_price"] * scale, r["high_price"] * scale, r["low_price"] * scale, r["close"] * scale,
                    r["volume"] * vol0 / 1e6))
    c = run[-1]["close"] * scale
    for k in range(1, post_days + 1):
        o = c * 0.97
        c2 = o * 0.93
        out.append((cal[d0_idx + k], o, o * 1.01, c2 * 0.98, c2, vol0 * 3))
        c = c2
    for i in range(d0_idx + post_days + 1, last + 1):
        out.append((cal[i], c, c * 1.02, c * 0.98, c, vol0))
    return out


def _flat(cal, p, v, gap_on=None, gap=0.0, end_idx=None, jump_on=None):
    out, c = [], p
    last = len(cal) - 1 if end_idx is None else end_idx
    for i in range(last + 1):
        o = c
        if gap_on and cal[i] == gap_on:
            o = c * (1.0 + gap)
            c = o
        if jump_on and cal[i] == jump_on:
            o = c * 1.8
            c = o
        out.append((cal[i], o, max(o, c) * 1.01, min(o, c) * 0.99, c, v))
    return out


FLAG_HDR = "check\tklass\tticker\tdate\tliquid\tgapn\tprev_close\topen\tclose\tgo\trc\tc1_over_pc\tc5_over_pc\tv_ratio_20\tdv20_prior\textra\n"


def build_tree(root: Path) -> dict:
    """The synthetic data tree (both eras on the real NYSE calendars), its facts for the dry run, and the shas for the pins override."""
    calA, calB = _nyse("2016-01-04", "2022-06-30"), _nyse("2021-09-27", "2024-12-31")
    assert len(calA) == 1635 and len(calB) == 821
    A = root / "cb702_pre_v2"
    B = root / "cb702"
    S = root / "cb702_pre" / "survivorship_1023"
    for d in (A / "audit_1023" / "price", B, S, root / "audit_runs_2026-10-23", root / "guardB"):
        d.mkdir(parents=True, exist_ok=True)
    a_d0, b_d0 = calA.index("2018-06-01"), calB.index("2023-06-01")
    eraA = {"SPY": _flat(calA, 100, 5e7),
            "AAA": _run_series(calA, a_d0, 10.0, 1e6),
            "BBB": _run_series(calA, calA.index("2019-09-03"), 0.4, 1e6, end_idx=calA.index("2020-06-30")),
            "OPLN": _flat(calA, 30, 1e6, gap_on="2019-06-28", gap=-0.62),
            "ZWS": _flat(calA, 40, 1e6, gap_on="2021-10-05", gap=-0.30),
            "EEE": _flat(calA, 20, 1e6, jump_on="2017-03-01"),
            "FFF": _flat(calA, 15, 1e6),
            "ABCDW": _flat(calA, 2, 1e6)}
    eraB = {"SPY": _flat(calB, 400, 5e7),
            "CCC": _run_series(calB, b_d0, 10.0, 1e6),
            "DDD": _run_series(calB, calB.index("2023-10-02"), 0.4, 1e6, end_idx=calB.index("2024-06-28")),
            # the two earlier-issuer controls, as on the real file: a ONE-session hole at the issuer switch
            "INBX": [r for r in _flat(calB, 34, 1e6) if r[0] != "2024-05-30"],
            "DOC": [r for r in _flat(calB, 11, 1e6) if r[0] != "2024-03-01"]}
    for path, era in ((A / "daily_closes_all.csv.gz", eraA), (B / "daily_closes_all.csv.gz", eraB)):
        with gzip.open(path, "wt") as fh:
            for t, rows in era.items():
                for r in rows:
                    fh.write(f"{t},{r[0]},{r[1]!r},{r[2]!r},{r[3]!r},{r[4]!r},{r[5]!r}\n")
            if era is eraB:
                fh.write("CCC,2025-01-02,1,1,1,1,1\n")                    # a sealed row: dropped at read, never seen
    with gzip.open(A / "daily_raw_close.csv.gz", "wt") as fh:
        for t, rows in eraA.items():
            for r in rows:
                fh.write(f"{t},{r[0]},{r[4]!r}\n")
    (A / "sessions.txt").write_text("\n".join(calA) + "\n")
    (A / "dedupe_applied.tsv").write_text("dropped_symbol\tkept_symbol\tfirst\tlast\tkind\trows\nXXX\tAAA\t2016-01-04\t2016-02-01\tretired_symbol\t20\n")
    (A / "small_pulls.psv").write_text("sectype|AAA|CS|XNAS\nsectype|BBB|CS|XNAS\nsectype|OPLN|CS|XNYS\nsectype|ZWS|CS|XNYS\nsectype|EEE|CS|XNYS\nsectype|FFF|CS|XNYS\n"
                                       "sectype|SPY|ETF|ARCX\nregime|2018-01-02|bull\n")
    (B / "small_pulls.psv").write_text("sectype|CCC|CS|XNAS\nsectype|SPY|ETF|ARCX\n")
    sic = "AAA|2026-10-16|200|1000|X|CS\n"
    (A / "cb702_sic.psv").write_text(sic)
    (B / "cb702_sic.psv").write_text(sic)
    (A / "symbol_guard.tsv").write_text("symbol\tbreaks\n" + "\n".join(f"{t}\t{'2017-03-01:jump' if t == 'EEE' else ''}" for t in sorted(eraA)) + "\n")
    (root / "guardB" / "symbol_guard_B.tsv").write_text("symbol\tbreaks\n")
    (A / "audit_1023" / "price" / "A_flags.tsv").write_text(FLAG_HDR + "adj_event\tx\tFFF\t2017-01-03\t0\t0\t1\t1\t1\t0\t0\t1\t1\t1\t1\t\n")
    (root / "audit_runs_2026-10-23" / "B_flags.tsv").write_text(FLAG_HDR + "adj_event\tx\tSPY\t2022-02-01\t0\t0\t1\t1\t1\t0\t0\t1\t1\t1\t1\t\n")
    (B / "cb702_splits.psv").write_text("")
    for f in ("export_stats.tsv",):
        (A / f).write_text("orig_rows\t1\n")
    (A / "audit_1023" / "verdict.txt").write_text("PASS\n")
    (S / "refetch_combined_records_1023.tsv").write_text("ticker\tname\ttype\tcik\tcomposite_figi\tshare_class_figi\tdelisted\n"
                                                          "BBB\tBeta Inc\tCS\t0000000002\t\t\t2020-06-30\n")
    (S / "stragglers_records.tsv").write_text("ticker\tname\ttype\tcik\tcomposite_figi\tshare_class_figi\tdelisted\nZZZQ\tZ\tCS\t0000000099\t\t\t2022-06-30\n")
    (root / "cb702_pre").mkdir(exist_ok=True)
    (root / "cb702_pre" / "symbol_guard.tsv").write_text("symbol\tbreaks\n" + "\n".join(t for t in sorted(eraA) if t != "BBB") + "\n")
    P = X.Paths(data=str(root), out=str(root / "ps314"), here=str(root / "here"), guard_B=str(root / "guardB" / "symbol_guard_B.tsv"),
                doc=str(root / "doc.md"), pins_override=str(root / "pins_override.json"))
    os.makedirs(P.here, exist_ok=True)
    reg = {}
    for k in X.REGISTERED_PINS:
        reg[k] = X.sha(os.path.join(REPO, X.LIVE_MODULES[k])) if k in X.LIVE_MODULES else X.sha(getattr(P, k))
    Path(P.pins_override).write_text(json.dumps(reg))
    nrows_A = sum(len(v) for v in eraA.values())
    facts = dict(X.FACTS)
    facts.update({
        "A_rows": nrows_A, "A_symbols": len(eraA), "A_sessions": 1635, "A_other_chars": 0, "A_suffix_W": 1, "A_suffix_U": 0, "A_suffix_R": 0,
        "A_ended_early": 1, "full_session_symbols": ("AAA", "OPLN"), "A_breaks": 1, "A_jump_only": 1, "A_hole_only": 0, "A_both": 0,
        "A_jump_symbols": 1, "A_jump_symbols_dv2m": 1, "fac_change_checks": (("EEE", "2017-03-01", False),), "guard_breaks_of": ("EEE", "2017-03-01:jump"),
        "fac_step_dates": (("AAA", ()), ("EEE", ())), "split_between_checks": (("AAA", "2018-02-10", "2018-02-20", False),),
        "dedupe_pairs": 1, "dedupe_rows": 20, "alias_outside_symbols": 0, "alias_outside_rows": 0, "alias_inside_rows": 0, "alias_rows": {},
        "alias_with_break": (), "adj_events_A": 1, "types_A_rows": 7, "types_A_symbols": 7, "types_A_twice": 0, "types_A_conflicts": 0,
        "sic_names": 1, "A_untyped_symbols": 1, "A_untyped_reach_2m": 0, "refetch_records": 1, "refetch_record_symbols": 1, "refetch_added": 1,
        "straggler_records": 1, "stragglers_owning": (), "blank_record_rows": {}, "A_refetched_nokey": 0, "A_refetched_nokey_dv2m": 0,
        "distribution_controls": (("OPLN", "2019-06-28"), ("ZWS", "2021-10-05")),
        "B_rows_total": sum(len(v) for v in eraB.values()) + 1, "B_rows_dropped": 1, "B_rows_kept": sum(len(v) for v in eraB.values()),
        "B_symbols_kept": len(eraB), "B_sessions": 821, "splits_after_file": 0, "adj_events_B": 1, "B_breaks": 0, "types_B_rows": 2, "sic_names": 1})
    return {"P": P, "facts": facts, "calA": calA, "calB": calB, "a_d0": calA[a_d0], "b_d0": calB[b_d0]}


def write_doc(P, extra_pins: dict = None) -> None:
    body = "# synthetic registration\n\nbody text\n\n"
    Path(P.doc).write_text(body + "<!-- FREEZE -->\n## Freeze record\n")
    pins = dict(extra_pins or {})
    pins["doc_body"] = X.doc_body_sha(P.doc)                 # the body above the marker is fixed, so its pin is known before the paste
    Path(P.doc).write_text(body + "<!-- FREEZE -->\n## Freeze record\n" + "".join(f"- {k}: `{v}`\n" for k, v in pins.items()))


REF_RECS = [
    {"ticker": "AAA", "name": "Alpha Corp", "type": "CS", "active": True, "cik": "0000000001", "composite_figi": "FA", "share_class_figi": "SA", "_pull": "active"},
    {"ticker": "OPLN", "name": "Openlane Inc", "type": "CS", "active": True, "cik": "0000000003", "composite_figi": "FO", "share_class_figi": "SO", "_pull": "active"},
    {"ticker": "ZWS", "name": "Zurn Elkay", "type": "CS", "active": True, "cik": "0000000004", "composite_figi": "FZ", "share_class_figi": "SZ", "_pull": "active"},
    {"ticker": "EEE", "name": "Echo Co", "type": "CS", "active": True, "cik": "0000000005", "composite_figi": "FE", "share_class_figi": "SE", "_pull": "active"},
    {"ticker": "CCC", "name": "Charlie Inc", "type": "CS", "active": True, "cik": "0000000006", "composite_figi": "FC", "share_class_figi": "SC", "_pull": "active"},
    {"ticker": "SPY", "name": "SPDR", "type": "ETF", "active": True, "cik": "", "composite_figi": "FS", "share_class_figi": "SS", "_pull": "active"},
    {"ticker": "BBB", "name": "Beta Inc", "type": "CS", "active": False, "cik": "0000000002", "delisted_utc": "2020-06-30T04:00:00Z", "_pull": "delisted"},
    {"ticker": "DDD", "name": "Delta Ltd", "type": "CS", "active": False, "cik": "0000000007", "delisted_utc": "2024-06-28T04:00:00Z", "_pull": "delisted"},
    {"ticker": "INBX", "name": "Inhibrx Inc", "type": "CS", "active": False, "cik": "0000000011", "delisted_utc": "2024-05-30T04:00:00Z", "_pull": "delisted"},
    {"ticker": "INBX", "name": "Inhibrx Biosciences", "type": "CS", "active": True, "cik": "0000000012", "_pull": "active"},
    {"ticker": "DOC", "name": "Physicians Realty", "type": "CS", "active": False, "cik": "0000000013", "delisted_utc": "2024-03-01T05:00:00Z", "_pull": "delisted"},
    {"ticker": "DOC", "name": "Healthpeak", "type": "CS", "active": True, "cik": "0000000014", "_pull": "active"},
    # R67: AAA traded as AAAO until 2019-01-02 (no bars under AAAO: era A keys the series by today's symbol)
    {"ticker": "AAAO", "name": "Alpha Corp", "type": "CS", "active": False, "cik": "0000000001", "composite_figi": "FA", "share_class_figi": "SA",
     "delisted_utc": "2019-01-02T05:00:00Z", "_pull": "delisted"},
]


def _sub_payload(name, recent):
    cols = ("form", "filingDate", "reportDate", "acceptanceDateTime", "accessionNumber", "primaryDocument", "items", "isXBRL")
    return {"name": name, "tickers": [], "filings": {"recent": {c: [r.get(c, "") for r in recent] for c in cols}, "files": []}}


def _fake_routes(tree) -> dict:
    a_d0 = tree["a_d0"]
    acc0 = (datetime.fromisoformat(a_d0) - timedelta(days=1)).strftime("%Y-%m-%dT21:30:00.000Z")       # after the close of D0 - 1
    subs = {
        "0000000001": _sub_payload("Alpha Corp", [
            {"form": "10-Q", "filingDate": "2018-05-01", "reportDate": "2018-03-31", "accessionNumber": "0000000001-18-000002", "primaryDocument": "a.htm"},
            {"form": "10-K", "filingDate": "2018-02-20", "reportDate": "2017-12-31", "accessionNumber": "0000000001-18-000001", "primaryDocument": "a.htm"},
            {"form": "8-K", "filingDate": a_d0, "acceptanceDateTime": acc0, "items": "2.02,9.01", "accessionNumber": "0000000001-18-000009"}]),
        "0000000002": _sub_payload("Beta Inc", [
            {"form": "10-Q", "filingDate": "2019-08-01", "reportDate": "2019-06-30", "accessionNumber": "0000000002-19-000001", "primaryDocument": "b.htm"}]),
        "0000000003": _sub_payload("Openlane Inc", [
            {"form": "8-K", "filingDate": "2019-06-28", "acceptanceDateTime": "2019-06-28T20:30:00.000Z", "items": "2.01,9.01", "accessionNumber": "3-1"}]),
        "0000000004": _sub_payload("Zurn Elkay", [
            {"form": "8-K", "filingDate": "2021-10-04", "acceptanceDateTime": "2021-10-04T21:00:00.000Z", "items": "2.01", "accessionNumber": "4-1"}]),
        "0000000006": _sub_payload("Charlie Inc", [
            {"form": "10-Q", "filingDate": "2023-05-05", "reportDate": "2023-03-31", "accessionNumber": "0000000006-23-000001", "primaryDocument": "c.htm"}]),
        "0000000007": _sub_payload("Delta Ltd", []),
    }
    facts = {
        "0000000001": {"entityName": "Alpha", "facts": {"dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": [
            {"accn": "0000000001-18-000002", "end": "2018-04-25", "val": 100_000_000, "filed": "2018-05-01", "form": "10-Q"},
            {"accn": "0000000001-18-000001", "end": "2018-02-10", "val": 100_000_000, "filed": "2018-02-20", "form": "10-K"}]}}},
            "us-gaap": {"NetIncomeLoss": {"units": {"USD": [
                {"accn": "x", "start": "2017-10-01", "end": "2017-12-31", "val": -5, "filed": "2018-02-20"},
                {"accn": "y", "start": "2018-01-01", "end": "2018-03-31", "val": 7, "filed": "2018-05-01"}]}}}}},
        "0000000006": {"entityName": "Charlie", "facts": {"dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": [
            {"accn": "0000000006-23-000001", "end": "2023-04-28", "val": 1_000_000_000, "filed": "2023-05-05", "form": "10-Q"}]}}}}},
    }
    r = {}
    for cik, p in subs.items():
        r[f"submissions/CIK{cik}.json"] = (200, p)
    for cik, p in facts.items():
        r[f"companyfacts/CIK{cik}.json"] = (200, p)
    idx = {"directory": {"item": [{"name": "aaa-20180331_htm.xml"}]}}
    r["/1/000000000118000002/index.json"] = (200, idx)
    r["/1/000000000118000002/aaa-20180331_htm.xml"] = (200, INSTANCE_XML.replace(b"2017-12-31", b"2018-03-31"))
    item = lambda t: {"title": f"{t} soars", "description": "growth", "published_utc": "2018-05-10T12:00:00Z", "tickers": [t],
                      "insights": [{"ticker": t, "sentiment": "positive"}], "publisher": {"name": "Wire"}}
    for t in ("AAA", "BBB", "CCC", "DDD"):
        r[f"ticker={t}"] = (200, {"results": [item(t)]})
    r["active=true"] = (200, {"results": [x for x in REF_RECS if x["_pull"] == "active"]})
    r["active=false"] = (200, {"results": [x for x in REF_RECS if x["_pull"] == "delisted"]})
    r[PL.ALPACA_CA] = (200, {"corporate_actions": {}})
    return r


def _pins_for_walk(P):
    p = X.pins(P, include_outputs=False)
    p["dryrun_printout"] = X.sha_or_absent(P.dry)
    for ph in RP.PHASES:
        p[f"step0_{ph}_printout"] = X.sha_or_absent(P.step0_printout(ph))
    p.pop("episodes", None)
    return p


@pytest.fixture(scope="module")
def tree(tmp_path_factory):
    return build_tree(tmp_path_factory.mktemp("ps314_tree"))


def test_step0_and_walk_gates_refuse_before_their_preconditions(tree, tmp_path):
    P = tree["P"]
    Q = X.Paths(**{**json.loads(RP.paths_to_json(P)), "here": str(tmp_path / "h"), "doc": str(tmp_path / "doc.md"), "out": str(tmp_path / "o")})
    os.makedirs(Q.here)
    pr = RP.gate_step0(Q, "derive")
    assert any("registration is missing" in q for q in pr) and any("dry run has not completed" in q for q in pr)
    assert any("polygon_reference pull is not in hand" in q for q in pr)
    write_doc(Q)
    Path(Q.dry).write_text("- modules: " + X.modules_line(Q) + "\nRESULT: 3 claims, 2 OK, 1 MISMATCH\nDRY RUN COMPLETE\n")
    pr = RP.gate_step0(Q, "derive")
    assert any("1 MISMATCH" in q for q in pr) and any("pins not below" in q for q in pr)
    Path(Q.dry).write_text("- modules: someone-else\nRESULT: 3 claims, 3 OK, 0 MISMATCH\nDRY RUN COMPLETE\n")
    assert any("other code" in q for q in RP.gate_step0(Q, "derive"))
    assert any("phase 'derive' has not run" in q for q in RP.gate_step0(Q, "climax"))
    pw = RP.gate_walk(Q)
    assert any("ABSENT" in q for q in pw) and any("has not run" in q for q in pw)


def test_the_dry_run_on_the_synthetic_tree_has_zero_mismatch(tree):
    P = tree["P"]
    rc = RP.dry_run(P, facts=tree["facts"])
    text = Path(P.dry).read_text()
    assert rc == 0, text[-3000:]
    assert X.printout_mismatches(P.dry) == 0, [ln for ln in text.splitlines() if "MISMATCH" in ln]
    assert X.dry_run_complete(P.dry) and "the flagger lists OPLN 2019-06-28" in text


def test_end_to_end_on_the_synthetic_tree(tree, monkeypatch):
    """dry run -> freeze -> STEP 0 derive (reference pull via ps_pull) -> EDGAR pull -> climax (three subprocesses) -> instances / news
    / Alpaca pulls -> features -> pins pasted -> walk (three subprocesses) -> G8 -> ps_rederive -> VERDICT MATCH. Every refusal on the
    way is a test failure."""
    P = tree["P"]
    if not X.dry_run_complete(P.dry):
        assert RP.dry_run(P, facts=tree["facts"]) == 0
    monkeypatch.setenv("POLYGON_API_KEY", "K")
    monkeypatch.setenv("ALPACA_PAPER_API_KEY", "a")
    monkeypatch.setenv("ALPACA_PAPER_SECRET_KEY", "b")
    write_doc(P, RP.frozen_pins(P))
    assert RP.gate_step0(P, "derive") == ["the polygon_reference pull is not in hand (%s): run ps_pull.py on the server first" % P.polygon_reference]
    os.makedirs(P.out, exist_ok=True)
    tr = PL.FakeTransport(_fake_routes(tree))
    PL.pull_reference(P, tr, say=lambda *_: None)
    from ps_common import Say
    assert ST.step0(P, "derive", Say()) == 0, Path(P.refused).read_text()[-4000:]
    derive_txt = Path(P.step0_printout("derive")).read_text()
    assert "candidate_ciks.txt" in derive_txt and Path(P.calendar_B).read_text().count("\n") == 821
    ciks = PL.read_ciks(P.candidate_ciks)
    assert {"0000000001", "0000000003", "0000000004"} <= set(ciks)
    assert ST.step0(P, "derive", Say()) == 2                                     # once means once
    PL.pull_edgar(P, tr, say=lambda *_: None, ciks=sorted(set(ciks) | {"0000000002", "0000000006", "0000000007"}))
    assert ST.step0(P, "climax", Say()) == 0, Path(P.refused).read_text()[-4000:]
    cl = X.read_tsv(P.climax_list)
    pops = {(r["population"], r["era"]) for r in cl}
    assert ("P1", "A") in pops and ("P2", "A") in pops and ("P1", "B") in pops and ("P2", "B") in pops
    assert all(r["calendar_file"] == (P.sessions_A if r["era"] == "A" else P.calendar_B) for r in cl)     # one calendar per record
    assert all(r["calendar_sha256"] == X.sha(r["calendar_file"]) for r in cl)
    aaa = [r for r in cl if r["ticker"] == "AAA" and r["population"] == "P1"]
    assert aaa and all(r["cap_source"] == "xbrl_cover_page" for r in aaa) and {r["tier"] for r in aaa} == {"mid"}
    bbb = [r for r in cl if r["ticker"] == "BBB" and r["population"] == "P2"]
    assert bbb and all(r["gone"] == "yes" and r["refetch_sourced"] == "1" for r in bbb)
    climax_txt = Path(P.step0_printout("climax")).read_text()
    assert "_MIN_DOLLAR_VOL_TODAY = 2,000,000" in climax_txt and "_MIN_DOLLAR_VOL_TODAY = 10,000,000" in climax_txt
    assert X.ledger_has_stage(P.ledger, "ps314_step0_derive:input:polygon_reference")                       # R66
    assert X.ledger_has_stage(P.ledger, "ps314_step0_climax:input:edgar_submissions")
    nw = X.read_tsv(P.news_wanted)                                                                          # R67
    assert {(w["d0_symbol"], w["symbol_status"]) for w in nw if w["ticker"] == "AAA"} == {("AAAO", "renamed")}
    assert {w["symbol_status"] for w in nw if w["ticker"] != "AAA"} <= {"series"}
    # R62: the subprocess entry points refuse when run by hand, whatever the gate says
    child = lambda *a: subprocess.run([sys.executable, str(BUILD / "ps_replay.py"), *a, "--paths-json", RP.paths_to_json(P)],
                                      capture_output=True, text=True)
    part1 = P.o("climax_part_P1.tsv")
    sha1 = X.sha(part1)
    r = child("--detect", "P1")
    assert r.returncode == 2 and "not launched by a gated parent" in r.stdout and X.sha(part1) == sha1
    Path(ST.claim_path(P, "--detect", "P1")).write_text("forged")                                           # a claim file without the token
    r = child("--detect", "P1")
    assert r.returncode == 2 and not os.path.exists(ST.claim_path(P, "--detect", "P1"))
    PL.pull_instances(P, tr, say=lambda *_: None)
    PL.pull_news(P, tr, say=lambda *_: None)
    PL.pull_alpaca_ca(P, tr, say=lambda *_: None)
    assert ST.step0(P, "features", Say()) == 0, Path(P.refused).read_text()[-4000:]
    feats = X.read_tsv(P.features)
    fa = [f for f in feats if f["ticker"] == "AAA" and f["population"] == "P1"]
    assert fa and all(f["earnings_flag"] in ("on_climax_day", "none") for f in fa)
    assert any(f["earnings_flag"] == "on_climax_day" for f in fa) and all(f["dilution_bucket"] in ("ge20", "lt20") for f in fa)
    cls = Path(P.step0_printout("features")).read_text()
    assert "OPLN 2019-06-28: class distribution" in cls and "ZWS 2021-10-05: class distribution" in cls
    assert {(f["news3_reason"], f["mna_reason"]) for f in feats if f["ticker"] == "AAA" and f["population"] in ("P1", "P2")} == {
        ("renamed_symbol", "renamed_symbol")}
    assert all(f["news3_reason"] != "renamed_symbol" for f in feats if f["ticker"] != "AAA")
    assert any("pins not below" in q for q in RP.gate_walk(P))
    r = child("--walk-pop", "P1")                                    # the reviewer's bypass: the gate refuses, the child must too
    assert r.returncode == 2 and not os.path.exists(P.o("episodes_part_P1.tsv")), r.stdout[-2000:]
    write_doc(P, _pins_for_walk(P))
    assert RP.gate_walk(P) == []
    r = child("--walk-pop", "P1")                                    # the gate passes; no parent claimed the run
    assert r.returncode == 2 and "not launched by a gated parent" in r.stdout and not os.path.exists(P.o("episodes_part_P1.tsv"))
    assert RP.gate_walk(P) == [] and not X.ledger_has_stage(P.ledger, "ps314_walk")
    rc = ST.walk(P, Say())
    assert rc == 0, Path(P.refused).read_text()[-5000:]
    res = Path(P.result).read_text()
    assert "VERDICT MATCH" in res and "WALK COMPLETE" in res and "G8 era A: entered after the cutoff 0" in res
    eps = X.read_tsv(P.episodes)
    assert {e["population"] for e in eps} == {"P1", "P2", "P2small"}
    assert all(e["era"] in ("A", "B") for e in eps)
    assert RP.gate_walk(P)                                                       # a second walk refuses
    # the re-derivation can FAIL: one settled R changed in a copy of episodes.tsv -> the numbers no longer match the runner's
    import pandas as pd
    mine = json.load(open(os.path.join(P.out, "ps_replay_numbers.json")))
    df = pd.read_csv(P.episodes, sep="\t", dtype=str, keep_default_na=False)
    k = df.index[(df["decision"] == "admitted") & (df["r5_status"] == "settled") & (df["population"] == "P1")][0]
    df.loc[k, "r5_r"] = str(float(df.loc[k, "r5_r"]) + 1.0)
    bad = os.path.join(P.out, "episodes_mutated.tsv")
    df.to_csv(bad, sep="\t", index=False)
    out = os.path.join(P.out, "rederive_mutated.json")
    assert subprocess.run([sys.executable, str(BUILD / "ps_rederive.py"), bad, out], capture_output=True).returncode == 0
    assert any(d.startswith("base:P1:pooled:mean_r") for d in ST.compare_numbers(mine, json.load(open(out))))


def test_the_rederivation_imports_nothing_of_the_runner():
    # source-pin-ok: independence is a property of the import graph — an independent recount must share no code with the runner, which no behaviour of either can prove
    import ast
    tree = ast.parse((BUILD / "ps_rederive.py").read_text())
    names = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    names |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    assert names <= {"json", "sys", "zlib", "numpy", "pandas"}, names


@pytest.mark.skipif(not REAL.exists(), reason="needs /Users/alvinfung/apollo_data (the real data tree)")
def test_real_tree_registered_pins_match_the_freeze_record():
    assert X.registered_pin_problems(X.LOCAL) == []
