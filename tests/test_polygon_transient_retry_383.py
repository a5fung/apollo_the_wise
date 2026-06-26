"""#383 — Polygon transient-timeout retry: a single blip retries silently; only a SUSTAINED
failure (all 3 attempts) goes loud. Regression for the 6/25 RYAAY spurious alert — one transient
timeout fired a Telegram, yet the same call returned 7439 bars 0.4s later."""
from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from agents.market_intelligence import collector


def _mock_async_client(get_side_effect):
    """Fake httpx.AsyncClient(...) — `async with` yields a client whose .get has the side-effect."""
    client = MagicMock()
    client.get = AsyncMock(side_effect=get_side_effect)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=client)
    cm.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=cm)


def _ok_response():
    r = MagicMock()
    r.status_code = 200
    r.raise_for_status = MagicMock()
    r.json = MagicMock(return_value={"results": [1, 2, 3]})
    return r


def _run_polygon(side_effect):
    alert = AsyncMock()
    with patch.dict(os.environ, {"POLYGON_API_KEY": "test-key"}), \
         patch.object(collector.httpx, "AsyncClient", _mock_async_client(side_effect)), \
         patch("agents.market_intelligence.llm_health.maybe_alert_api_failure", alert), \
         patch.object(collector.asyncio, "sleep", AsyncMock()):
        try:
            out = asyncio.run(collector._polygon_get("/v2/aggs/x"))
            return out, alert, None
        except Exception as e:  # noqa: BLE001 — test inspects the raised type
            return None, alert, e


def test_383_single_transient_timeout_retries_then_succeeds_no_alert():
    out, alert, exc = _run_polygon([httpx.ReadTimeout("blip"), _ok_response()])
    assert exc is None
    assert out == {"results": [1, 2, 3]}
    alert.assert_not_called()  # a recovered transient must NOT cry wolf


def test_383_sustained_timeout_reraises_and_alerts():
    out, alert, exc = _run_polygon(
        [httpx.ReadTimeout("1"), httpx.ReadTimeout("2"), httpx.ReadTimeout("3")]
    )
    assert isinstance(exc, httpx.TransportError)  # sustained → propagates to the caller
    alert.assert_called_once()  # sustained → loud
