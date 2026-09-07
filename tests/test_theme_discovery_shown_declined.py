"""#486 (2026-09-07) — the discovery recorder: what the model was SHOWN vs what it DECLINED.

Step 3 measured that 140 of 398 themes had >=half their founders sitting in a stored
correlation cluster a median 26 sessions before the theme was born, and
`_discover_new_themes` is already handed `correlation_clusters` — so those groups were in
front of the model and it passed on them. Nothing recorded that: the discovery audit row
carried only token counts. These tests freeze the recorder that makes "why did it decline?"
answerable, and freeze the two properties that keep it safe: it changes nothing, and it
never raises.
"""
import json
from unittest.mock import AsyncMock, patch

import pytest

from agents.market_intelligence import theme_engine as te


def _cluster(h, tickers, corr=0.88, rs=71.0):
    return {"cluster_hash": h, "tickers": list(tickers),
            "member_count": len(tickers), "mean_corr": corr, "avg_rs": rs}


def _stock(tk):
    return {"ticker": tk}


@pytest.mark.asyncio
async def test_records_declined_tickers_and_untouched_clusters():
    pools = {
        "uncovered": [_stock("AAA"), _stock("BBB"), _stock("CCC")],
        "velocity": [_stock("DDD")],
        "turner": [],
        "elite": [],
    }
    clusters = [
        _cluster("h_taken", ["AAA", "BBB"]),      # fully claimed
        _cluster("h_declined", ["XXX", "YYY"]),   # nothing claimed -> the finding
        _cluster("h_partial", ["CCC", "ZZZ"]),    # half claimed
    ]
    proposed = [{"name": "Some theme", "tickers": ["aaa", "BBB", "CCC"]}]

    with patch.object(te, "log_audit_event", new=AsyncMock()) as m:
        await te._log_discovery_shown_and_declined(
            pools, clusters, proposed, recall_mode=False)

    assert m.await_count == 1
    event_type, summary, detail = m.await_args.args
    assert event_type == "theme_discovery_shown_declined"
    d = json.loads(detail)

    # DDD was shown and never claimed; the lowercase "aaa" must still count as claimed.
    assert d["declined"]["uncovered"] == []
    assert d["declined"]["velocity"] == ["DDD"]

    # Only the cluster with zero claimed members is reported as declined, with its members.
    assert [c["cluster_hash"] for c in d["clusters_declined"]] == ["h_declined"]
    assert d["clusters_declined"][0]["tickers"] == ["XXX", "YYY"]
    assert d["clusters_partial"] == 1
    assert d["clusters_taken"] == 1
    assert "declined=1" in summary and "partial=1" in summary and "taken=1" in summary


@pytest.mark.asyncio
async def test_recorder_never_raises_on_malformed_input():
    """A recorder must never be able to break discovery — this is why it is wrapped."""
    with patch.object(te, "log_audit_event", new=AsyncMock()) as m:
        await te._log_discovery_shown_and_declined(
            {"uncovered": [{"ticker": None}]},
            [{"cluster_hash": "h", "tickers": None, "mean_corr": None, "avg_rs": None}],
            [{"name": "x", "tickers": None}],
            recall_mode=True,
        )
    assert m.await_count <= 1  # wrote or skipped, but did not raise


@pytest.mark.asyncio
async def test_a_failing_recorder_does_not_change_what_discovery_returns():
    """THE LINE: the row is written AFTER the result exists and cannot alter it."""
    returned = [{"name": "T", "tickers": ["AAA"]}]
    with patch.object(te, "_discover_new_themes_single",
                      new=AsyncMock(return_value=returned)), \
         patch.object(te, "log_audit_event",
                      new=AsyncMock(side_effect=RuntimeError("audit down"))):
        out = await te._discover_new_themes(
            [_stock("AAA")], [], {"AAA": _stock("AAA")},
            correlation_clusters=[_cluster("h", ["AAA"])])
    assert out == returned
