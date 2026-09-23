"""#400a — get_runtime_toggle: DB row overrides env; env fallback on no-row/error;
60s cache keeps reads off hot paths. (Replaces test_yoy_shadow_decision.py —
the #149 shadow + its helper were retired 2026-07-02, superseded by the #321
LIVE recovery whose revert toggle this tests.)"""
import pytest
from unittest.mock import AsyncMock, patch

from agents.market_intelligence import db as dbmod
from tests.conftest import make_mock_pool


@pytest.fixture(autouse=True)
def _fresh_cache():
    dbmod._runtime_toggle_cache.clear()
    yield
    dbmod._runtime_toggle_cache.clear()


def _pool_with_row(row):
    pool, conn = make_mock_pool()
    conn.fetchrow = AsyncMock(return_value=row)
    return pool, conn


@pytest.mark.asyncio
async def test_db_row_off_overrides_env_true(monkeypatch):
    monkeypatch.setenv("T400_FLAG", "true")
    pool, _ = _pool_with_row({"state": "off"})
    with patch.object(dbmod, "get_pool", AsyncMock(return_value=pool)):
        assert await dbmod.get_runtime_toggle("t400", "T400_FLAG") is False


@pytest.mark.asyncio
async def test_db_row_on_overrides_env_false(monkeypatch):
    monkeypatch.setenv("T400_FLAG", "false")
    pool, _ = _pool_with_row({"state": "on"})
    with patch.object(dbmod, "get_pool", AsyncMock(return_value=pool)):
        assert await dbmod.get_runtime_toggle("t400", "T400_FLAG") is True


@pytest.mark.asyncio
async def test_no_row_falls_back_to_env(monkeypatch):
    monkeypatch.setenv("T400_FLAG", "false")
    pool, _ = _pool_with_row(None)
    with patch.object(dbmod, "get_pool", AsyncMock(return_value=pool)):
        assert await dbmod.get_runtime_toggle("t400", "T400_FLAG") is False


@pytest.mark.asyncio
async def test_no_row_no_env_uses_default(monkeypatch):
    monkeypatch.delenv("T400_FLAG", raising=False)
    pool, _ = _pool_with_row(None)
    with patch.object(dbmod, "get_pool", AsyncMock(return_value=pool)):
        assert await dbmod.get_runtime_toggle("t400", "T400_FLAG", default=True) is True


@pytest.mark.asyncio
async def test_db_error_fails_open_to_env(monkeypatch):
    monkeypatch.setenv("T400_FLAG", "true")
    with patch.object(dbmod, "get_pool", AsyncMock(side_effect=RuntimeError("db down"))):
        assert await dbmod.get_runtime_toggle("t400", "T400_FLAG") is True


@pytest.mark.asyncio
async def test_cache_prevents_second_read(monkeypatch):
    monkeypatch.setenv("T400_FLAG", "true")
    pool, conn = _pool_with_row({"state": "off"})
    with patch.object(dbmod, "get_pool", AsyncMock(return_value=pool)):
        assert await dbmod.get_runtime_toggle("t400", "T400_FLAG") is False
        assert await dbmod.get_runtime_toggle("t400", "T400_FLAG") is False
    assert conn.fetchrow.await_count == 1, "second call within TTL must hit the cache"
