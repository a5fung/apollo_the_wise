"""The #486 discovery recorder must get its evidence on the BATCHED path — the only one prod uses.

WHY (found 2026-09-10, verifying #486). `_discover_new_themes` has two branches. The single-batch
branch passed `existing_themes` and `scratchpads` to `_log_discovery_shown_and_declined`; the
BATCHED branch passed neither. `_DISCOVERY_LLM_BATCH_STOCKS` is 22 and the nightly pool runs 60-70
names, so the single-batch branch never executes in production — every live run recorded:

  * `scratchpads: []`  — the "why did the model decline this cluster?" instrument, empty every night
  * `already_named: 0` — pinned to 0 by construction, because the cluster/theme overlap is computed
    from `existing_themes`, which arrived as None

The summary line read healthy throughout (`declined=6 already_named=0`), which is exactly what makes
this the week's recurring defect: a field whose value is fixed by the call site cannot be evidence.
Both branches are asserted below so the two cannot drift apart again.
"""
import pytest

from agents.market_intelligence import theme_engine as te


def _stock(tk):
    return {"ticker": tk, "rs_rank": 80.0, "sector": "Tech"}


def _setup(monkeypatch, n_stocks):
    """Capture the recorder's kwargs; make the LLM step append a scratchpad like the real one."""
    seen = {}

    async def _fake_single(*a, **kw):
        kw["advisor_state"].setdefault("scratchpads", []).append("declined: no shared driver")
        return []

    async def _fake_record(pools, clusters, proposed, **kw):
        seen.update(kw)

    monkeypatch.setattr(te, "_discover_new_themes_single", _fake_single)
    monkeypatch.setattr(te, "_log_discovery_shown_and_declined", _fake_record)

    stocks = [_stock(f"T{i}") for i in range(n_stocks)]
    themes = [{"name": "AI infra", "tickers": ["T0", "T1"], "stage": "Accelerating"}]
    return seen, stocks, themes


@pytest.mark.asyncio
async def test_batched_path_passes_scratchpads_and_themes(monkeypatch):
    """The live path. 40 stocks > the batch size of 22, so this is what prod runs every night."""
    seen, stocks, themes = _setup(monkeypatch, 40)
    await te._discover_new_themes(stocks, themes, {s["ticker"]: s for s in stocks})

    assert seen.get("scratchpads"), (
        "the batched path recorded NO scratchpads — the #486 'why did it decline' instrument is "
        "dead on the only path production uses")
    assert seen.get("existing_themes"), (
        "the batched path passed no existing_themes — `already_named` and `covered_by` are then "
        "pinned to 0/[] by construction and cannot be read as evidence")


@pytest.mark.asyncio
async def test_single_batch_path_still_passes_both(monkeypatch):
    """The fast path had it right; it must not lose it while the other is being fixed."""
    seen, stocks, themes = _setup(monkeypatch, 5)
    await te._discover_new_themes(stocks, themes, {s["ticker"]: s for s in stocks})

    assert seen.get("scratchpads")
    assert seen.get("existing_themes")


def test_the_pool_size_that_makes_this_matter():
    """Guard the premise: if the batch size ever rose above the real pool, the live path would flip.

    Documented so a future change to _DISCOVERY_LLM_BATCH_STOCKS re-reads this file rather than
    silently making the untested branch the live one again.
    """
    assert te._DISCOVERY_LLM_BATCH_STOCKS < 60, (
        "prod discovery pools run 60-70 names; if the batch ceiling passes that, the SINGLE-batch "
        "branch becomes the live path and this file's assumptions invert")
