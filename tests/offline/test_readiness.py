"""Exercise the registered HTTP route without lifespan, stores or providers."""

import asyncio
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
from redis.asyncio import Redis, from_url

from src import main


class Connection:
    def __init__(self, failure=None, wait=None, value=1):
        self.failure = failure
        self.wait = wait
        self.value = value
        self.statements = []
        self.closed = False

    async def __aenter__(self):
        if self.failure == "enter":
            raise RuntimeError("fictional-database-secret")
        return self

    async def __aexit__(self, *_args):
        self.closed = True
        if self.failure == "exit":
            raise RuntimeError("fictional-database-secret")

    async def execute(self, statement):
        self.statements.append(str(statement))
        if self.wait is not None:
            await self.wait.wait()
        if self.failure == "execute":
            raise RuntimeError("fictional-database-secret")
        return SimpleNamespace(scalar_one=lambda: self.value)


class Cache:
    def __init__(self, *, value=True, failure=None, wait=None, close_wait=None):
        self.value = value
        self.failure = failure
        self.wait = wait
        self.close_wait = close_wait
        self.pings = 0
        self.closes = 0
        self.entered = asyncio.Event()

    async def ping(self):
        self.pings += 1
        self.entered.set()
        if self.wait is not None:
            await self.wait.wait()
        if self.failure == "ping":
            raise RuntimeError("fictional-cache-secret")
        return self.value

    async def aclose(self):
        self.closes += 1
        if self.close_wait is not None:
            await self.close_wait.wait()
        if self.failure == "close":
            raise RuntimeError("fictional-cache-secret")


class ReadinessTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.connection = Connection()
        self.cache = Cache()
        self.patches = [
            patch.object(
                main, "read_engine", SimpleNamespace(connect=lambda: self.connection)
            ),
            patch.object(main, "is_cache_enabled", return_value=True),
            patch.object(
                main.settings.CACHE,
                "URL",
                "redis://fixture:fictional-secret@fixture.invalid:6379/0?suppress=true",
            ),
            patch.object(
                main.redis_asyncio,
                "from_url",
                side_effect=lambda *_a, **_kw: self.cache,
            ),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=main.app), base_url="http://fixture"
        )
        self.addAsyncCleanup(self.client.aclose)

    async def response(self, status, database, cache):
        response = await self.client.get("/readyz")
        self.assertEqual(response.status_code, status)
        self.assertEqual(
            response.json(),
            {
                "status": "ready" if status == 200 else "unavailable",
                "checks": {"database": database, "cache": cache},
            },
        )
        self.assertEqual(response.headers["cache-control"], "no-store")
        return response

    async def test_actual_route_checks_dependencies_and_releases_both(self):
        await self.response(200, "ok", "ok")
        self.assertEqual(self.connection.statements, ["SELECT 1"])
        self.assertTrue(self.connection.closed)
        self.assertEqual((self.cache.pings, self.cache.closes), (1, 1))

    async def test_liveness_does_not_access_dependencies(self):
        with patch.object(
            main.read_engine, "connect", side_effect=AssertionError("no probe")
        ):
            response = await self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        self.assertEqual(self.cache.pings, 0)

    async def test_disabled_cache_is_honest_and_never_constructed(self):
        with (
            patch.object(main, "is_cache_enabled", return_value=False),
            patch.object(
                main.redis_asyncio, "from_url", side_effect=AssertionError("disabled")
            ),
        ):
            await self.response(200, "ok", "disabled")

    async def test_database_acquisition_failure_skips_cache(self):
        with patch.object(
            main.read_engine, "connect", side_effect=RuntimeError("fictional-secret")
        ):
            await self.response(503, "unavailable", "not_checked")
        self.assertEqual(self.cache.pings, 0)

    async def test_database_enter_query_and_cleanup_failure_are_unavailable(self):
        for phase in ("enter", "execute", "exit"):
            with self.subTest(phase=phase):
                self.connection = Connection(failure=phase)
                await self.response(503, "unavailable", "not_checked")
                self.assertEqual(self.connection.closed, phase != "enter")
        self.assertEqual(self.cache.pings, 0)

    async def test_unexpected_database_value_fails_closed(self):
        self.connection.value = 2
        await self.response(503, "unavailable", "not_checked")

    async def test_database_timeout_releases_connection(self):
        self.connection.wait = asyncio.Event()
        with patch.object(main, "_READINESS_PROBE_SECONDS", 0.01):
            await asyncio.wait_for(self.response(503, "unavailable", "not_checked"), 1)
        self.assertTrue(self.connection.closed)

    async def test_redis_factory_failure_does_not_mask_database_success(self):
        with patch.object(
            main.redis_asyncio,
            "from_url",
            side_effect=ValueError("fictional-url-secret"),
        ):
            await self.response(503, "ok", "unavailable")

    async def test_cache_false_or_unexpected_ping_is_not_ready(self):
        for value in (False, None, "PONG", 1):
            with self.subTest(value=value):
                self.cache = Cache(value=value)
                await self.response(503, "ok", "unavailable")
                self.assertEqual(self.cache.closes, 1)

    async def test_cache_ping_and_close_failures_are_unavailable_and_redacted(self):
        for phase in ("ping", "close"):
            with self.subTest(phase=phase):
                self.cache = Cache(failure=phase)
                response = await self.response(503, "ok", "unavailable")
                self.assertNotIn("secret", response.text)
                self.assertEqual(self.cache.closes, 1)

    async def test_cache_timeout_still_closes(self):
        self.cache.wait = asyncio.Event()
        with patch.object(main, "_READINESS_PROBE_SECONDS", 0.01):
            await asyncio.wait_for(self.response(503, "ok", "unavailable"), 1)
        self.assertEqual(self.cache.closes, 1)

    async def test_cache_close_timeout_cannot_report_ready(self):
        self.cache.close_wait = asyncio.Event()
        with patch.object(main, "_READINESS_CLOSE_SECONDS", 0.01):
            await asyncio.wait_for(self.response(503, "ok", "unavailable"), 1)

    async def test_transport_query_options_survive_cashews_option_removal(self):
        url = "rediss://fixture:fictional-secret@fixture.invalid:6380/0?suppress=true&db=3&ssl_cert_reqs=required&socket_timeout=0.75"
        factory = from_url
        with (
            patch.object(main.settings.CACHE, "URL", url),
            patch.object(main.redis_asyncio, "from_url", wraps=factory) as create,
            patch.object(Redis, "ping", new=AsyncMock(return_value=True)),
            patch.object(Redis, "aclose", new=AsyncMock(return_value=None)),
        ):
            await self.response(200, "ok", "ok")
        self.assertNotIn("suppress", create.call_args.args[0])
        # Check real Redis parsing without connecting to a server.
        actual = factory(create.call_args.args[0])
        kwargs = actual.connection_pool.connection_kwargs
        self.assertEqual(kwargs["db"], 3)
        self.assertEqual(kwargs["ssl_cert_reqs"], "required")
        self.assertEqual(kwargs["socket_timeout"], 0.75)
        await actual.aclose()

    async def test_failure_then_recovery_is_rechecked(self):
        self.cache.failure = "ping"
        await self.response(503, "ok", "unavailable")
        self.cache.failure = None
        await self.response(200, "ok", "ok")
        self.assertEqual(self.cache.pings, 2)

    async def test_concurrent_requests_own_their_status_and_cache_clients(self):
        clients = [Cache(value=(index % 2 == 0)) for index in range(12)]
        with patch.object(main.redis_asyncio, "from_url", side_effect=clients):
            responses = await asyncio.gather(
                *[self.client.get("/readyz") for _ in clients]
            )
        self.assertEqual(
            sorted(response.status_code for response in responses),
            [200] * 6 + [503] * 6,
        )
        self.assertTrue(
            all((client.pings, client.closes) == (1, 1) for client in clients)
        )

    async def test_request_cancellation_closes_cache_without_success(self):
        self.cache.wait = asyncio.Event()
        request = asyncio.create_task(self.client.get("/readyz"))
        await asyncio.wait_for(self.cache.entered.wait(), 1)
        request.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await request
        self.assertEqual(self.cache.closes, 1)

    async def test_compose_health_command_targets_actual_ready_route(self):
        import yaml

        path = Path(__file__).resolve().parents[2] / "docker-compose.yml.example"
        config = yaml.safe_load(path.read_text())
        command = config["services"]["api"]["healthcheck"]["test"][-1]
        self.assertIn("http://localhost:8000/readyz", command)
        await self.response(200, "ok", "ok")


if __name__ == "__main__":
    unittest.main()
