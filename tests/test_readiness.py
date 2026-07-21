"""Unit coverage for the dependency-aware Honcho readiness gate."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src import main


class _Connection:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def execute(self, _statement):
        return None


class _Engine:
    def connect(self):
        return _Connection()


@pytest.mark.asyncio
async def test_readyz_returns_ready_when_database_and_cache_are_available(monkeypatch):
    redis_client = MagicMock()
    redis_client.ping = AsyncMock()
    redis_client.aclose = AsyncMock()

    monkeypatch.setattr(main, "engine", _Engine())
    monkeypatch.setattr(main, "is_cache_enabled", lambda: True)
    monkeypatch.setattr(
        main.redis_asyncio,
        "from_url",
        MagicMock(return_value=redis_client),
    )

    response = await main.readiness_check()

    assert response.status_code == 200
    assert response.body == b'{"status":"ready","checks":{"database":"ok","cache":"ok"}}'
    redis_client.ping.assert_awaited_once()
    redis_client.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_readyz_fails_closed_when_database_is_unavailable(monkeypatch):
    class _BrokenEngine:
        def connect(self):
            raise ConnectionError("database unavailable")

    monkeypatch.setattr(main, "engine", _BrokenEngine())

    response = await main.readiness_check()

    assert response.status_code == 503
    assert response.body == b'{"status":"unavailable","checks":{"database":"required","cache":"required"}}'


@pytest.mark.asyncio
async def test_readyz_strips_cache_only_query_parameters_from_direct_redis_probe(monkeypatch):
    redis_client = MagicMock()
    redis_client.ping = AsyncMock()
    redis_client.aclose = AsyncMock()

    monkeypatch.setattr(main, "engine", _Engine())
    monkeypatch.setattr(main, "is_cache_enabled", lambda: True)
    from_url = MagicMock(return_value=redis_client)
    monkeypatch.setattr(main.redis_asyncio, "from_url", from_url)
    monkeypatch.setattr(main.settings.CACHE, "URL", "redis://redis:6379/0?suppress=true")

    response = await main.readiness_check()

    assert response.status_code == 200
    from_url.assert_called_once_with("redis://redis:6379/0")