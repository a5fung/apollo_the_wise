"""A keyword match may no longer overrule a contrary classification (#516, operator-signed).

The operator ruled 8 M&A suppressions across #514 and 2026-08-08. **7 were false positives.**
Every one of the four keyword-path misfires — LII, SCZM, SOUN, UMAC — had ALREADY been graded by
our own classifier as something OTHER than M&A (`routine`), and was suppressed anyway because a
word like "merger" or "takeover" appeared somewhere in the text.

SOUN is the clearest: its own stored summary says the move was *"driven primarily by a blowout Q2
earnings print and upgraded forward guidance"*, the filter classified the catalyst `routine`, and
it was killed on the word "merger". Not a judgment call that went the wrong way — a keyword match
on text that explicitly attributes the move to something else.

⚠ **The rule is deliberately NARROWER than "require the classifier to concur", and that
distinction is the whole design.** CLRO — the ONE correct suppression in the ruled set — has **no
classification at all** (killed at the `9m_intraday` detector before grading ran). Requiring
concurrence would have RELEASED a real deal. This guard cannot touch it.

Measured over 73 fires in 60 days: 28 where the classifier agrees stay suppressed, 27 with no
classification are unaffected, 18 released — of which the 4 ruled are confirmed false positives.
"""
import asyncio

from agents.market_intelligence.ma_filter import is_likely_ma


def _run(coro):
    return asyncio.run(coro)


_KEYWORD_TEXT = ["gap driven by a blowout Q2 earnings print; a merger was mentioned elsewhere"]


def test_the_SOUN_case_is_no_longer_suppressed():
    """The exact shape he ruled on: our grader said `routine`, a keyword appeared anyway."""
    fired, _ = _run(is_likely_ma("SOUN", catalyst_quality="routine",
                                 catalyst_texts=_KEYWORD_TEXT, check_polygon=False))
    assert fired is False, (
        "a keyword match is overruling a contrary classification again — this is the LII/SCZM/"
        "SOUN/UMAC false-positive class the operator ruled on")


def test_the_CLRO_case_is_UNCHANGED():
    """THE most important test here. CLRO is the one CORRECT suppression, and it has NO
    classification — so the guard must not apply. A broader rule ('require the classifier to
    concur') would have released a real deal, and I nearly proposed exactly that."""
    fired, meta = _run(is_likely_ma("CLRO", catalyst_quality=None,
                                    catalyst_texts=["Announces Entry into Merger Agreement"],
                                    check_polygon=False))
    assert fired is True, (
        "the guard is now vetoing suppressions that have NO classification — that releases "
        "CLRO, the known true positive")
    assert meta and meta["source"].startswith("keyword_in_text")


def test_the_classifier_AGREEING_still_suppresses():
    fired, meta = _run(is_likely_ma("X", catalyst_quality="mna",
                                    catalyst_texts=["definitive merger agreement to acquire X"],
                                    check_polygon=False))
    assert fired is True and meta["source"] == "claude_classifier"


def test_an_empty_classification_is_treated_as_NO_VERDICT_not_as_disagreement():
    """`None` and `""` both mean "we never formed a view" — neither may veto. Treating an empty
    string as disagreement would silently release every ungraded name, which is the CLRO risk
    by another route."""
    for q in (None, ""):
        fired, _ = _run(is_likely_ma("Z", catalyst_quality=q,
                                     catalyst_texts=["Merger Agreement announced"],
                                     check_polygon=False))
        assert fired is True, f"catalyst_quality={q!r} wrongly vetoed the keyword path"


def test_the_polygon_path_is_deliberately_NOT_gated():
    """WEN (x5), LCID (x2) and FRMI all fired via polygon_news with NO classification, so gating
    that path here would do nothing — and it is a SEPARATE problem the operator has parked. If
    someone later extends the guard over polygon, this test should make them stop and think."""
    import inspect
    src = inspect.getsource(is_likely_ma)
    after = src.split("if check_polygon:")[1]
    assert "_classifier_disagrees" not in after, (
        "the guard now gates the polygon_news path too — that was explicitly out of scope and "
        "parked by the operator, and it changes suppressions he has not ruled on")


def test_telemetry_cannot_change_the_verdict():
    """The veto writes an audit row. A DB failure there must never alter the filter's answer —
    the local run proved this by failing to log with no DB and still returning False."""
    import inspect
    src = inspect.getsource(is_likely_ma)
    seg = src.split("mna_keyword_vetoed_by_classifier")[1][:600]
    assert "except Exception" in seg, "the veto telemetry is no longer isolated"


def test_the_veto_is_only_recorded_when_it_CHANGED_something():
    """If it logged on every graded name, the row count would be noise instead of a direct
    measure of the rule's effect."""
    import inspect
    src = inspect.getsource(is_likely_ma)
    assert "_would_have = matches_mna_in_any(catalyst_texts)" in src, (
        "the veto now logs without checking a keyword would actually have matched")


# ── 2026-08-30 additions — DoD-3 (match_path) + a real WEN-adjacent dedup bug found live ──────

def test_match_path_is_set_on_every_source_not_just_polygon():
    """DoD-3: `detail.match_path` used to be set on only the two polygon_news sub-paths.
    scripts/_b88_mna_filter_path_b_fp_rate.py buckets anything missing it as 'unknown' with
    no fallback rule for keyword_in_text_N, which is exactly how the '70% unknown' reading
    happened. `source` always identified every row (confirmed in docs/analysis/
    516_ma_filter_false_positives_2026-08-08.md) — this just makes the same fact queryable
    from the JSON `detail` blob the script actually parses."""
    fired, meta = _run(is_likely_ma("Y", catalyst_quality="mna",
                                    catalyst_texts=["definitive merger agreement to acquire Y"],
                                    check_polygon=False))
    assert fired is True and meta["match_path"] == "claude_classifier"

    fired, meta = _run(is_likely_ma("SOUN2", catalyst_quality=None,
                                    catalyst_texts=_KEYWORD_TEXT, check_polygon=False))
    assert fired is True and meta["match_path"] == "keyword_in_text_0"


def test_CLRO_match_path_still_identifies_the_keyword_path():
    """Same CLRO case as above, checking the new field doesn't disturb the existing one."""
    fired, meta = _run(is_likely_ma("CLRO", catalyst_quality=None,
                                    catalyst_texts=["Announces Entry into Merger Agreement"],
                                    check_polygon=False))
    assert fired is True
    assert meta["match_path"].startswith("keyword_in_text")


def test_veto_telemetry_is_deduped_per_ticker_per_day():
    """Found live 2026-08-19: TEM logged `mna_keyword_vetoed_by_classifier` twice, 9 minutes
    apart, on the same trading day — this telemetry stream never got the (ticker, day) dedup
    its #89/#284 siblings have. Audit-noise-only: the filter's return value is identical
    whether or not the row gets written, so this is plumbing, not a criteria change."""
    import inspect
    from agents.market_intelligence import ma_filter
    src = inspect.getsource(ma_filter.is_likely_ma)
    assert "should_log_mna_veto(ticker)" in src, (
        "the veto write is no longer gated by should_log_mna_veto — TEM-class double-logging "
        "is back")


def test_should_log_mna_veto_dedups_per_ticker_per_ET_day(monkeypatch):
    """Direct unit test of the new dedup helper's SQL shape: a prior same-day row -> False."""
    from agents.market_intelligence import ma_filter

    class _FakeConn:
        def __init__(self, prior):
            self._prior = prior

        async def fetchrow(self, query, *args):
            assert "mna_keyword_vetoed_by_classifier" in query
            assert args[0] == "TEM: %"
            return self._prior

    class _FakeAcquire:
        def __init__(self, conn):
            self._conn = conn

        async def __aenter__(self):
            return self._conn

        async def __aexit__(self, *a):
            return False

    class _FakePool:
        def __init__(self, conn):
            self._conn = conn

        def acquire(self):
            return _FakeAcquire(self._conn)

    async def _get_pool_no_prior():
        return _FakePool(_FakeConn(None))

    async def _get_pool_has_prior():
        return _FakePool(_FakeConn({"1": 1}))

    import agents.market_intelligence.db as db_mod

    monkeypatch.setattr(db_mod, "get_pool", _get_pool_no_prior)
    assert _run(ma_filter.should_log_mna_veto("TEM")) is True

    monkeypatch.setattr(db_mod, "get_pool", _get_pool_has_prior)
    assert _run(ma_filter.should_log_mna_veto("TEM")) is False
