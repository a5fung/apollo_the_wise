"""#679 fixed ONE of eleven call sites; the default still said an outage was a finding.

FOUND 2026-09-21 by the day's simplify review (altitude angle). `search_news_perplexity` returns
`""` when the provider says "there is no news about this name" AND when the provider never
answered at all. #679 made the difference reachable at exactly one caller by adding an opt-in
`raise_on_failure=True` — `theme_engine._news_check`, the site where the conflation had already
demoted four themes Mainstream -> Nascent on 2026-09-04 and stripped every member ticker's EP
theme bonus. The other ten callers, INCLUDING both EP catalyst paths, still could not tell the
two apart. "Failure is not a finding" was enforced by whoever remembered the flag.

THE FIX IS A `str` SUBCLASS, and that shape is the point. A typed exception cannot be the default
here: `ep_detector._fetch_perplexity_answer` is awaited inside a `gather(return_exceptions=True)`
whose consumer re-raises the first exception, so raising by default would abort that whole
enrichment step. `NewsAnswer` behaves as the exact `str` every caller already handles — so no
call site could be broken by the migration — while carrying `.provider_failed` so any of them can
ask. The information stops being destroyed at the boundary.

⚠ WHAT THIS DELIBERATELY DOES NOT DO: re-grade. Whether a corpus missing its news leg should
change an EP grade is a detection-criterion question, and this repo does not write rules without
measured harm. The EP sites RECORD the degradation (`ep_corpus_missing_news_provider`, L3) so the
question can be answered from data later. [[no-rules-without-measured-harm]]
"""
from __future__ import annotations

import ast
import asyncio
from pathlib import Path

import httpx
import pytest

import agents.market_intelligence.collector as collector
from agents.market_intelligence.collector import NewsAnswer

REPO = Path(__file__).resolve().parents[1]
_REQ = httpx.Request("POST", "https://api.perplexity.ai/v1/agent")


@pytest.fixture(autouse=True)
def _stubs(monkeypatch):
    monkeypatch.setenv("PERPLEXITY_API_KEY", "k")
    collector._PPLX_CACHE.clear()

    async def _no_sleep(_s): return None
    monkeypatch.setattr(collector.asyncio, "sleep", _no_sleep)

    async def _quiet(*a, **k): return None
    import agents.market_intelligence.llm_health as llm_health
    monkeypatch.setattr(llm_health, "triage_perplexity_exception", _quiet, raising=False)
    monkeypatch.setattr(llm_health, "alert_perplexity_invalid_json", _quiet, raising=False)
    monkeypatch.setattr(llm_health, "alert_perplexity_empty_answer", _quiet, raising=False)


def _install(monkeypatch, behaviors: list):
    class _Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, *a, **k):
            b = behaviors.pop(0)
            if isinstance(b, Exception):
                raise b
            return b
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: _Client())


def _status_error(code: int) -> httpx.HTTPStatusError:
    resp = httpx.Response(code, text="", request=_REQ)
    try:
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        return e
    raise AssertionError("expected a raise")


class _Answer:
    """A SUCCESSFUL provider answer that happens to say there is no news — the case that must
    NOT be recorded as a failure. `output` is found by `type == "message"`, never by index."""
    status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        return {"status": "completed",
                "output": [{"type": "message",
                            "content": [{"type": "output_text",
                                         "text": "No news of any kind about this company."}]}],
                "usage": {}}


# ── the property that was missing ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_an_outage_and_a_genuine_no_news_answer_are_no_longer_the_same_value(monkeypatch):
    """THE defect, stated as one assertion. Before today both of these were `""`."""
    _install(monkeypatch, [_status_error(500), _status_error(500)])
    outage = await collector.search_news_perplexity("why did X gap")
    collector._PPLX_CACHE.clear()
    _install(monkeypatch, [_Answer()])
    real = await collector.search_news_perplexity("why did Y gap", fresh=True)

    assert outage.provider_failed is True, "an outage still reads as a real answer"
    assert real.provider_failed is False, "a genuine answer is being reported as an outage"
    assert outage != real or not real, (
        "the two are indistinguishable again — which is the whole defect, not a detail"
    )


@pytest.mark.asyncio
async def test_a_genuine_no_news_answer_is_still_a_real_finding(monkeypatch):
    """The other direction, and the one that is easy to break. A provider that successfully says
    "there is nothing here" must NOT be recorded as a failure — that would turn every quiet name
    into a phantom outage and make the new flag useless."""
    _install(monkeypatch, [_Answer()])
    out = await collector.search_news_perplexity("why did Z gap")
    assert out.provider_failed is False
    assert "No news" in out


@pytest.mark.asyncio
async def test_a_missing_api_key_is_a_failure_not_an_empty_finding(monkeypatch):
    monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)
    out = await collector.search_news_perplexity("why did X gap")
    assert out.provider_failed is True and out.failure_reason == "no_api_key"
    assert out == "", "the fail-open VALUE must not change — only what we know about it"


@pytest.mark.asyncio
async def test_the_failure_names_its_own_cause(monkeypatch):
    _install(monkeypatch, [_status_error(429), _status_error(429)])
    out = await collector.search_news_perplexity("why did X gap")
    assert out.provider_failed is True
    assert out.failure_reason, "a failure with no reason tells a later reader nothing"


# ── the migration must not have changed behaviour anywhere ───────────────────────────────────

@pytest.mark.asyncio
async def test_it_is_still_a_plain_string_to_every_existing_caller(monkeypatch):
    """Eleven call sites slice, truncate, join, compare and falsify this value. If `NewsAnswer`
    stopped behaving as `str`, the migration would break code nowhere near this file."""
    _install(monkeypatch, [_Answer()])
    out = await collector.search_news_perplexity("why did X gap")
    assert isinstance(out, str)
    assert out[:7] == "No news" and out.lower().startswith("no news")
    assert "\n".join([out, "x"]).endswith("x")
    assert bool(out) is True
    assert bool(NewsAnswer("", provider_failed=True)) is False, (
        "a failed read must stay FALSY — every existing `if answer:` fallback depends on it"
    )
    assert NewsAnswer("abc") == "abc" and {"abc": 1}[NewsAnswer("abc")] == 1


def test_no_call_site_was_left_reading_a_bare_string_by_accident():
    """DERIVED, not hand-listed: every production caller resolves to this one function, so the
    property is carried by the return type rather than by eleven remembered opt-ins. This states
    the count so a NEW caller shows up as a number change and gets read."""
    hits = []
    for root in ("agents", "core", "channels"):
        for f in sorted((REPO / root).rglob("*.py")):
            try:
                tree = ast.parse(f.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                fn = node.func if isinstance(node, ast.Call) else None
                name = (fn.id if isinstance(fn, ast.Name)
                        else fn.attr if isinstance(fn, ast.Attribute) else None)
                if name == "search_news_perplexity":
                    hits.append(f"{f.relative_to(REPO)}:{node.lineno}")
    assert len(hits) == 11, (
        f"the production call-site count moved to {len(hits)}: {hits}. That is not a failure — "
        f"read the new one and confirm it treats a provider outage as UNAVAILABLE rather than as "
        f"a factual 'no news', then update this number."
    )


@pytest.mark.asyncio
async def test_the_EP_path_records_a_degraded_corpus_instead_of_losing_it(monkeypatch):
    """The EP half. It must WRITE the degradation — and must not write one on a healthy read."""
    from agents.market_intelligence import ep_detector
    rows: list = []

    # ⚠ THE STUB MIRRORS THE REAL SIGNATURE EXACTLY — no `**kw`. The first version of this test
    # took `**kw` and therefore passed while the code under it called `log_audit_event(...,
    # severity="L3")`, a parameter that does not exist. A permissive stub does not test a call,
    # it hides one. The binding assertion below is the belt to this brace.
    async def _cap(event_type, summary, detail="", *, conn=None):
        rows.append((event_type, summary))
    monkeypatch.setattr(ep_detector, "log_audit_event", _cap)

    failed = await ep_detector._note_if_news_provider_failed(
        NewsAnswer(provider_failed=True, failure_reason="timeout"), "ARHS", "enriched corpus")
    assert failed is True
    await _drain()                                    # the write is fire-and-forget by design
    assert len(rows) == 1
    assert rows[0][0] == "ep_corpus_missing_news_provider" and "ARHS" in rows[0][1]

    ok = await ep_detector._note_if_news_provider_failed(
        NewsAnswer("a real catalyst"), "ARHS", "enriched corpus")
    await _drain()
    assert ok is False and len(rows) == 1, "a healthy read wrote a phantom outage row"


def test_the_audit_call_actually_matches_the_real_function():
    """Bind the call against the REAL `log_audit_event` signature. A monkeypatched stub can only
    ever prove the code matches the STUB — which is how `severity="L3"` survived a green test and
    would have raised TypeError on the first genuine Perplexity outage, inside a gather whose
    consumer re-raises, taking the whole enriched corpus with it."""
    import inspect
    from agents.market_intelligence.db import log_audit_event
    sig = inspect.signature(log_audit_event)
    assert "severity" not in sig.parameters, (
        "log_audit_event gained a `severity` parameter — re-read the call in "
        "`_note_if_news_provider_failed`, which was written once assuming it had one."
    )
    sig.bind("ep_corpus_missing_news_provider", "ARHS: enriched corpus — provider did not answer")


async def _drain() -> None:
    """Let the fire-and-forget audit task run. The write is deliberately NOT awaited by the
    caller, so a test that asserts on it has to await the task itself.

    ⚠ NOT via `asyncio.sleep(0)`. The autouse fixture above replaces `collector.asyncio.sleep` —
    and `collector.asyncio` IS the one `asyncio` module object, so that patch neuters
    `asyncio.sleep` for the WHOLE PROCESS, this file's own calls included. Anything here that
    leans on sleep semantics is testing the stub."""
    from agents.market_intelligence import ep_detector
    if ep_detector._PENDING_PROVIDER_NOTES:
        await asyncio.gather(*list(ep_detector._PENDING_PROVIDER_NOTES),
                             return_exceptions=True)


@pytest.mark.asyncio
async def test_the_audit_write_is_NEVER_awaited_on_the_grading_path(monkeypatch):
    """⚠ THE REGRESSION THIS ALMOST SHIPPED. Both callers sit inside the sequential
    `for c in candidates[:SHORTLIST_SIZE]` grading loop, and `log_audit_event` is timeout-bounded
    at 5s (#621). Awaiting it meant a Perplexity outage during 9:30-9:45 ET cost up to 5s PER
    SHORTLISTED NAME — with SHORTLIST_SIZE=20, worse than the 22.5s retry regression fixed hours
    earlier the same night, and added by the fix for it.

    Exercised by making the write HANG: the caller must still return immediately. Re-await the
    write inside `_note_if_news_provider_failed` and this deadlocks the test."""
    from agents.market_intelligence import ep_detector
    started = asyncio.Event()
    never = asyncio.get_running_loop().create_future()

    # ⚠ A FUTURE THAT NEVER RESOLVES, NOT `asyncio.sleep(3600)`. The first draft used sleep and
    # PASSED under the mutation that re-awaits the write — because the autouse fixture patches
    # `collector.asyncio.sleep`, and `collector.asyncio` is the one `asyncio` module object, so
    # every sleep in the process returns instantly. The test was measuring the stub.
    async def _hang(*a, **k):
        started.set()
        await never
    monkeypatch.setattr(ep_detector, "log_audit_event", _hang)

    out = await asyncio.wait_for(
        ep_detector._note_if_news_provider_failed(
            NewsAnswer(provider_failed=True, failure_reason="timeout"), "ARHS", "enriched corpus"),
        timeout=2,
    )
    assert out is True, "the caller did not get its answer while the audit write was still running"
    # It had NOT started when the caller returned — that is the point — so wait for it now.
    await asyncio.wait_for(started.wait(), timeout=1)
    assert started.is_set(), "the write never actually started — fire-and-forget became fire-never"
    never.cancel()
    for task in list(ep_detector._PENDING_PROVIDER_NOTES):
        task.cancel()


@pytest.mark.asyncio
async def test_the_pending_write_is_held_so_it_cannot_be_collected(monkeypatch):
    """asyncio holds only a WEAK reference to a task. A bare `create_task(...)` whose handle
    nobody keeps can be garbage-collected before it runs, and the row would vanish silently —
    the worst failure mode for a recorder."""
    from agents.market_intelligence import ep_detector
    seen: list = []

    # No sleep here either — see _drain's note. A bare coroutine still yields at `await`.
    async def _slow(event_type, summary, detail="", *, conn=None):
        seen.append(event_type)
    monkeypatch.setattr(ep_detector, "log_audit_event", _slow)

    await ep_detector._note_if_news_provider_failed(
        NewsAnswer(provider_failed=True, failure_reason="timeout"), "ARHS", "enriched corpus")
    assert ep_detector._PENDING_PROVIDER_NOTES, "nothing is holding the in-flight write"
    await _drain()
    assert seen == ["ep_corpus_missing_news_provider"]
    assert not ep_detector._PENDING_PROVIDER_NOTES, "the done-callback never discarded the task"


@pytest.mark.asyncio
async def test_a_failure_to_RECORD_never_costs_the_name_its_grade(monkeypatch):
    """The wrap, exercised. A recording write that raises must be swallowed — the grading path it
    observes cannot be the thing it breaks."""
    from agents.market_intelligence import ep_detector

    async def _explode(*a, **k):
        raise RuntimeError("audit table is gone")
    monkeypatch.setattr(ep_detector, "log_audit_event", _explode)
    out = await ep_detector._note_if_news_provider_failed(
        NewsAnswer(provider_failed=True, failure_reason="timeout"), "ARHS", "enriched corpus")
    assert out is True, "a logging failure changed what the caller is told about the provider"
    await _drain()  # and the raised exception must not escape the background task either


@pytest.mark.asyncio
async def test_a_200_with_no_extractable_text_is_a_FAILURE_not_a_no_news_finding(monkeypatch):
    """A vendor changing its response shape raises NO exception — the HTTP call succeeds and the
    body simply yields nothing. Every other signal stays silent, so this is the outage class the
    flag most needs to carry. The function already ALERTS here and its own comment calls it "the
    response shape breaking"; it was still returning provider_failed=False.

    ⚠ The distinction that keeps this honest: a genuine "no information found" comes back as HEDGE
    TEXT, never as a blank — so this cannot swallow a real negative finding."""
    class _Blank:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {"status": "completed", "output": [], "usage": {}}

    import agents.market_intelligence.llm_health as llm_health
    monkeypatch.setattr(llm_health, "alert_perplexity_empty_answer",
                        lambda *a, **k: _noop(), raising=False)

    async def _noop(): return None
    _install(monkeypatch, [_Blank()])
    out = await collector.search_news_perplexity("why did X gap", fresh=True)
    assert out == "", "the fail-open VALUE changed — only the flag was supposed to move"
    assert out.provider_failed is True, (
        "a 200 whose body yields nothing is still recorded as the factual verdict 'no news'"
    )
    assert out.failure_reason == "empty_200"
