"""#697 item 6 — the HTF labelled corpus is pinned BY KIND, and the by-kind checker is proven to bite.

Why this file exists: until 2026-10-11 the corpus was eight flat members ("his examples") and the replay
test treated them alike — so ATAI, a NEGATIVE the raw function still scores COILED, tripped a
"MUST-NOT-MISS" message, and his June consolidation examples (GH, HNGE-June) and the HPE pointer had no
home at all (they were "stated by inspection of the bars, not replayed" — htf_scope_2026-10-10.md §8).
`tests/fixtures/htf_labelled.py` now carries a `label_kind` per member; `check_member` in
`tests/test_htf_labelled_corpus.py` asserts by kind on the replay of every member. THIS file proves:

  1. the corpus holds exactly the members the scope doc names, under the right kind;
  2. every new-kind label quotes his own words and the quote is VERBATIM in the cited repo doc;
  3. only the `htf` kind enters the hit tally (GH / HNGE-June must never be counted as HTF hits);
  4. the checker FAILS on deliberately wrong members (a green checker that cannot fail is theatre) —
     each violation of the contract is constructed and must raise.

What would make this file red on the pre-change tree: `label_kind` / `known_miss_gate` / `closed_by` /
`quote_file` do not exist on origin/main's fixture (AttributeError at import), and GH / HPE have no bars.
"""
from __future__ import annotations

import dataclasses
import re
from datetime import date, timedelta
from pathlib import Path

import pytest

from agents.market_intelligence import flag_detector as fd
from tests.fixtures.htf_labelled import HTF_LABELLED, LABEL_KINDS, POSITIVE_KINDS
from tests.test_htf_labelled_corpus import (
    _PRE_TRADE_SESSIONS,
    _load_bars,
    check_member,
    check_member_static,
    hit_tally,
    member_id,
    pushable_before,
    replay_member,
)

_ROOT = Path(__file__).resolve().parents[1]
_BY_KEY = {(m.ticker, m.label_date): m for m in HTF_LABELLED}


def _m(ticker: str, label_date: date):
    return _BY_KEY[(ticker, label_date)]


# ── 1. the corpus, by kind ───────────────────────────────────────────────────────────────────

def test_every_member_declares_a_valid_kind():
    assert HTF_LABELLED
    for m in HTF_LABELLED:
        assert m.label_kind in LABEL_KINDS, (m.ticker, m.label_date, m.label_kind)
    assert set(POSITIVE_KINDS) <= set(LABEL_KINDS)


def test_corpus_holds_the_scope_doc_members_under_their_kind():
    """htf_scope_2026-10-10.md §2: 2a three labelled HTFs, 2b two consolidation examples, 2c one
    pointer, 2d five negatives. A SUBSET check on purpose — a further member is a one-line fixture
    addition (docs/setups/htf.md known limitation 6), not a second edit here."""
    required = {
        ("CDNA", date(2026, 8, 19)): "htf",
        ("HNGE", date(2026, 8, 24)): "htf",
        ("MRNA", date(2026, 9, 17)): "htf",
        ("GH", date(2026, 6, 27)): "consolidation",
        ("HNGE", date(2026, 6, 27)): "consolidation",
        ("HPE", date(2026, 6, 2)): "pointer",
        ("NCI", date(2026, 6, 27)): "negative",
        ("ATAI", date(2026, 7, 24)): "negative",
        ("OUST", date(2026, 9, 4)): "negative",
        ("SHAZ", date(2026, 9, 4)): "negative",
        ("REPL", date(2026, 9, 4)): "negative",
    }
    have = {k: m.label_kind for k, m in _BY_KEY.items()}
    missing = {k: v for k, v in required.items() if have.get(k) != v}
    assert not missing, f"corpus lost or re-kinded a scope-doc member: {missing} (have {have})"
    assert len(_BY_KEY) == len(HTF_LABELLED), "two members share (ticker, label_date)"


def test_one_ticker_can_hold_two_kinds_without_collision():
    """HNGE is both the August HTF call (a known miss at the pole floor) and the June consolidation
    example — two members, two kinds, never merged."""
    august, june = _m("HNGE", date(2026, 8, 24)), _m("HNGE", date(2026, 6, 27))
    assert (august.label_kind, june.label_kind) == ("htf", "consolidation")
    assert member_id(august) != member_id(june)


# ── 2. labels are his words, verbatim ────────────────────────────────────────────────────────

def _norm(s: str) -> str:
    s = s.replace("’", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", s).strip()


def quote_in_doc(quote: str, doc: str) -> bool:
    return _norm(quote) in _norm((_ROOT / doc).read_text())


_QUOTED = [m for m in HTF_LABELLED if m.quote_file]


def test_the_new_kinds_all_carry_a_quote_file():
    new_kind = [m for m in HTF_LABELLED if m.label_kind in ("consolidation", "pointer")]
    assert {m.ticker for m in new_kind} >= {"GH", "HNGE", "HPE"}
    assert all(m.quote_file for m in new_kind)
    assert _QUOTED, "no member carries a quote_file — the verbatim check below would be vacuous"


@pytest.mark.parametrize("member", _QUOTED, ids=[member_id(m) for m in _QUOTED])
def test_trader_read_is_verbatim_in_its_source_doc(member):
    assert quote_in_doc(member.trader_read, member.quote_file), (
        f"{member.ticker} {member.label_date}: trader_read is not verbatim in {member.quote_file} — "
        f"labels come from his own words, never a paraphrase")


def test_the_verbatim_check_can_fail():
    assert not quote_in_doc("a sentence he never said about a coil", "docs/methodology/operator_shared_notes.md")


# ── 3. the replay, by kind, and the hit tally ────────────────────────────────────────────────

@pytest.fixture(scope="module")
def replays():
    bars = _load_bars()
    return {member_id(m): replay_member(m, bars) for m in HTF_LABELLED}


def test_every_member_obeys_its_kind_on_the_shipped_detector(replays):
    for m in HTF_LABELLED:
        check_member(m, replays[member_id(m)])


def test_only_the_htf_kind_enters_the_hit_tally(replays):
    """Scope doc §2a: 'hit rate on his labelled HTFs' counts HTF-kind members only. GH / HNGE-June are
    family positives and HPE a pointer — counting them would tune the HTF pole on names he never
    called an HTF."""
    by_id = {member_id(m): m for m in HTF_LABELLED}
    tally = hit_tally(HTF_LABELLED, replays)
    htf = [m for m in HTF_LABELLED if m.label_kind == "htf"]
    assert tally["n"] == len(htf) >= 3 and tally["n"] < len(HTF_LABELLED)
    assert set(tally["caught"]) == {member_id(m) for m in htf if m.expected == "actionable"}, (
        "the replay and the declarations disagree on which HTFs were caught")
    assert all(by_id[i].label_kind == "htf" for i in tally["caught"])
    assert not any(i.startswith(("GH_", "HPE_")) or i.startswith("HNGE_2026-06") for i in tally["caught"])


def test_the_tally_ignores_a_non_htf_member_even_when_the_detector_pushes_it():
    """Construct the failure the kinds exist to prevent: a consolidation that IS pushable before its
    date. It must not move the HTF hit count."""
    caught = _synthetic(["TIGHTENING"] + ["unqualified"] * 4, on_label=("WATCH", "runup_95%"))
    htf_hit, cons = _member(_CDNA, expected="actionable"), _member(_GH, expected="actionable")
    tally = hit_tally([htf_hit, cons], {member_id(htf_hit): caught, member_id(cons): caught})
    assert tally == {"n": 1, "caught": [member_id(htf_hit)]}


def test_declared_june_misses_name_the_gate_the_replay_actually_hits(replays):
    """GH and HNGE-June: the replayable gate is the 90% pole floor (79% / 67%), measured by replay —
    not 'by inspection' (htf_scope_2026-10-10.md §8 said the replay had not been done)."""
    gh, hnge = _m("GH", date(2026, 6, 27)), _m("HNGE", date(2026, 6, 27))
    for m in (gh, hnge):
        assert m.known_miss_gate == "runup_"
        for d in m.assert_dates:
            row = replays[member_id(m)][d]
            assert (row["reason"] or "").startswith("runup_"), (m.ticker, d, row["reason"])
            assert row["runup_pct"] < 0.90, (m.ticker, d, row["runup_pct"])
    assert 0.78 < replays[member_id(gh)][date(2026, 6, 24)]["runup_pct"] < 0.80
    assert 0.66 < replays[member_id(hnge)][date(2026, 6, 24)]["runup_pct"] < 0.68


def test_loosening_the_pole_floor_flips_the_declared_misses_loudly(monkeypatch):
    """The corpus must RESPOND to the shipped detector, not just agree with it today: re-run the real
    replay with the retired n=1 pole ratio (1.50 instead of 1.90) and the declared misses must fail —
    HNGE-August reaches COILED (its declaration is stale: 'CLOSED'), the June consolidation examples
    stop reading `runup_` (the recorded verdict moved). Measured 2026-10-11."""
    bars = _load_bars()
    monkeypatch.setattr(fd, "_RUNUP_MIN_RATIO", 1.5)
    with pytest.raises(AssertionError, match="CLOSED"):
        aug = _m("HNGE", date(2026, 8, 24))
        check_member(aug, replay_member(aug, bars))
    for key in (("GH", date(2026, 6, 27)), ("HNGE", date(2026, 6, 27))):
        m = _m(*key)
        with pytest.raises(AssertionError, match="RECORDED verdict changed"):
            check_member(m, replay_member(m, bars))
    cdna = _m("CDNA", date(2026, 8, 19))          # the caught one stays caught
    check_member(cdna, replay_member(cdna, bars))


def test_the_pointer_is_never_scored_as_a_hit(replays):
    hpe = _m("HPE", date(2026, 6, 2))
    res = replays[member_id(hpe)]
    assert hpe.label_kind == "pointer" and hpe.expected.startswith("rejected:")
    assert res[date(2026, 6, 2)]["stage"] not in ("WATCH", "TIGHTENING", "COILED", "TRIGGERED")
    assert not pushable_before(hpe.label_date, res)


# ── 4. the checker bites — each contract violation is constructed and must raise ─────────────

_LABEL = date(2026, 7, 10)


def _synthetic(prior_stages, on_label=("unqualified", "runup_50%_below_90%")):
    """res for a member labelled `_LABEL`: one scan row per calendar day before it (oldest first),
    plus the label day itself."""
    n = len(prior_stages)
    res = {}
    for i, stage in enumerate(prior_stages):
        d = _LABEL - timedelta(days=n - i)
        res[d] = {"stage": stage, "reason": f"{stage.lower()}_row", "runup_pct": 0.5}
    res[_LABEL] = {"stage": on_label[0], "reason": on_label[1], "runup_pct": 0.5}
    return res


def _member(base, **kw):
    return dataclasses.replace(base, label_date=_LABEL, assert_dates=(_LABEL,), replay_from=None, **kw)


_CDNA = _m("CDNA", date(2026, 8, 19))
_HNGE_AUG = _m("HNGE", date(2026, 8, 24))
_GH = _m("GH", date(2026, 6, 27))
_HPE = _m("HPE", date(2026, 6, 2))
_ATAI = _m("ATAI", date(2026, 7, 24))
_OUST = _m("OUST", date(2026, 9, 4))

_QUIET = ["unqualified"] * 5


def test_the_checker_passes_a_well_formed_member_at_the_window_edge():
    # the 5th scan session before the label counts (the scope doc's own CDNA-second-flag edge) …
    ok = _member(_CDNA, expected="actionable", known_miss_gate="")
    check_member(ok, _synthetic(["TIGHTENING", "unqualified", "unqualified", "unqualified", "unqualified"],
                                on_label=("WATCH", "runup_95%")))
    assert _PRE_TRADE_SESSIONS == 5


@pytest.mark.parametrize("label, member, res, fragment", [
    ("htf caught nowhere before its date",
     _member(_CDNA, expected="actionable", known_miss_gate=""),
     _synthetic(_QUIET, on_label=("WATCH", "runup_95%")), "MUST-NOT-MISS"),
    ("a pushable read ON the label day is not 'before the trade'",
     _member(_CDNA, expected="actionable", known_miss_gate=""),
     _synthetic(_QUIET, on_label=("TIGHTENING", "range_0.9")), "MUST-NOT-MISS"),
    ("a pushable read 6 sessions back is outside the 5-session window",
     _member(_CDNA, expected="actionable", known_miss_gate=""),
     _synthetic(["TIGHTENING", "unqualified", "unqualified", "unqualified", "unqualified", "unqualified"],
                on_label=("WATCH", "runup_95%")), "MUST-NOT-MISS"),
    ("an uncaught htf with no declared gate is an unexplained miss",
     _member(_HNGE_AUG, expected="rejected:runup_", known_miss_gate=""),
     _synthetic(_QUIET), "DECLARED known miss"),
    ("the declared gate must be the gate that fires",
     _member(_HNGE_AUG, expected="rejected:runup_", known_miss_gate="flag_low_"),
     _synthetic(_QUIET), "does not match"),
    ("a declared miss the detector now catches is a stale declaration",
     _member(_HNGE_AUG, expected="rejected:runup_", known_miss_gate="runup_"),
     _synthetic(["unqualified", "unqualified", "unqualified", "TIGHTENING", "unqualified"]), "CLOSED"),
    ("a consolidation is held to the same reach-or-declare rule",
     _member(_GH, expected="rejected:runup_", known_miss_gate=""),
     _synthetic(_QUIET), "DECLARED known miss"),
    ("a pointer asserted as a hit",
     _member(_HPE, expected="actionable"),
     _synthetic(_QUIET, on_label=("WATCH", "runup_95%")), "never asserted as a hit"),
    ("a negative the function scores actionable must name the layer that closes it",
     _member(_ATAI, expected="actionable", closed_by=""),
     _synthetic(_QUIET, on_label=("COILED", "range_1.0")), "closed_by"),
    ("closed_by on a rejected negative is decoration",
     _member(_OUST, expected="rejected:runup_", closed_by="a layer"),
     _synthetic(_QUIET), "closed_by only applies"),
    ("a consolidation without a verbatim source doc",
     _member(_GH, expected="rejected:runup_", known_miss_gate="runup_", quote_file=""),
     _synthetic(_QUIET), "quote_file"),
    ("an unknown kind",
     _member(_CDNA, expected="actionable", label_kind="setup"),
     _synthetic(_QUIET), "label_kind must be one of"),
    ("known_miss_gate on a negative",
     _member(_OUST, expected="rejected:runup_", known_miss_gate="runup_"),
     _synthetic(_QUIET), "known_miss_gate only applies"),
    ("a caught htf that still carries a miss declaration",
     _member(_CDNA, expected="actionable", known_miss_gate="runup_"),
     _synthetic(["TIGHTENING"] + ["unqualified"] * 4, on_label=("WATCH", "runup_95%")), "not both"),
])
def test_the_checker_raises_on_a_wrong_member(label, member, res, fragment):
    with pytest.raises(AssertionError) as exc:
        check_member(member, res)
    assert fragment in str(exc.value), f"{label}: raised, but not for the reason under test: {exc.value}"


def test_a_negative_that_stops_leaking_says_recorded_verdict_not_must_not_miss():
    """The mislabel this fixes: ATAI (negative, expected 'actionable') used to fire the HTF
    'MUST-NOT-MISS regressed' message when the function stopped scoring it. It is a recorded LEAK."""
    stopped = _synthetic(_QUIET, on_label=("unqualified", "mna_filter:deal_pin_fresh"))
    with pytest.raises(AssertionError) as exc:
        check_member(_member(_ATAI, expected="actionable"), stopped)
    assert "RECORDED verdict" in str(exc.value) and "MUST-NOT-MISS" not in str(exc.value)


def test_a_well_formed_negative_leak_and_pointer_pass():
    check_member(_member(_ATAI, expected="actionable"), _synthetic(_QUIET, on_label=("COILED", "range_1.0")))
    check_member(_member(_HPE, expected="rejected:base_age_"),
                 _synthetic(_QUIET, on_label=("unqualified", "base_age_0_below_3")))


def test_static_contract_rejects_a_kindless_looking_member():
    with pytest.raises(AssertionError):
        check_member_static(dataclasses.replace(_CDNA, label_kind=""))
