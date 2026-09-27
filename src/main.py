import asyncio
import logging
import re
import uuid
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, cast
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import sentry_sdk
from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi_pagination import add_pagination
from pydantic import ValidationError
from redis import asyncio as redis_asyncio
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration
from sqlalchemy import text

from src._version import HONCHO_VERSION
from src.cache.client import close_cache, init_cache, is_cache_enabled
from src.config import settings
from src.db import (
    engine,
    read_engine,
    register_db_query_instrumentation,
    request_context,
)
from src.dev_tools import setup_dev_tools
from src.exceptions import HonchoException
from src.routers import (
    conclusions,
    hypotheses,
    inductions,
    keys,
    messages,
    peers,
    predictions,
    sessions,
    traces,
    webhooks,
    workspaces,
)
from src.startup import validate_embedding_schema
from src.telemetry import (
    initialize_telemetry_async,
    metrics_endpoint,
    prometheus_metrics,
    register_db_pool_collector,
    shutdown_telemetry,
)
from src.telemetry.logging import get_route_template
from src.telemetry.sentry import initialize_sentry

if TYPE_CHECKING:
    from sentry_sdk._types import Event, Hint


def get_log_level() -> int:
    """
    Convert log level string from settings to logging module constant.

    Returns:
        int: The logging level constant (e.g., logging.INFO)
    """
    log_level_str = settings.LOG_LEVEL.upper()

    log_levels = {
        "CRITICAL": logging.CRITICAL,  # 50
        "ERROR": logging.ERROR,  # 40
        "WARNING": logging.WARNING,  # 30
        "INFO": logging.INFO,  # 20
        "DEBUG": logging.DEBUG,  # 10
        "NOTSET": logging.NOTSET,  # 0
    }

    return log_levels.get(log_level_str, logging.INFO)


# Configure logging
logging.basicConfig(
    level=get_log_level(),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)
_READINESS_PROBE_SECONDS = 1.5
_READINESS_CLOSE_SECONDS = 0.25

# Suppress cashews Redis error logs (NoScriptError, ConnectionError, etc.)
# These are handled gracefully by SafeRedis and don't need full tracebacks
logging.getLogger("cashews.backends.redis.client").setLevel(logging.CRITICAL)


class MetricsAccessFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        return "GET /metrics" not in msg


logging.getLogger("uvicorn.access").addFilter(MetricsAccessFilter())


def before_send(event: "Event", hint: "Hint | None") -> "Event | None":
    """Filter out events raised from known non-actionable exceptions before Sentry sees them."""
    if not hint:
        return event

    exc_info = hint.get("exc_info")
    if not exc_info:
        return event

    _, exc_value, _ = exc_info
    if isinstance(exc_value, HonchoException):
        return None

    # Filters out ValidationErrors and RequestValidationErrors (typically coming from Pydantic)
    if isinstance(exc_value, ValidationError | RequestValidationError):
        logger.info(f"Filtering out validation error from Sentry: {exc_value}")
        return None

    return event


# Sentry Setup
SENTRY_ENABLED = settings.SENTRY.ENABLED
if SENTRY_ENABLED:
    initialize_sentry(
        integrations=[
            StarletteIntegration(
                transaction_style="endpoint",
            ),
            FastApiIntegration(
                transaction_style="endpoint",
            ),
            # Explicit so DB-query spans are not reliant on auto-enabling.
            SqlalchemyIntegration(),
        ],
        before_send=before_send,
    )


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Initialize CloudEvents telemetry
    await initialize_telemetry_async()

    # Expose DB connection-pool stats for this API instance (no-op if metrics off)
    register_db_pool_collector("api")
    register_db_query_instrumentation("api")

    # Validate embedding schema before serving any traffic. Fails closed: if
    # the configured EMBEDDING_VECTOR_DIMENSIONS does not match the physical
    # pgvector columns, the process refuses to start rather than silently
    # writing wrong-dim vectors.
    await validate_embedding_schema(engine)

    try:
        await init_cache()
    except Exception as e:
        logger.warning(
            "Error initializing cache in api process; proceeding without cache: %s", e
        )

    try:
        yield
    finally:
        # Import here to avoid circular import at module load time
        from src.vector_store import close_external_vector_store

        await close_external_vector_store()
        await close_cache()
        await engine.dispose()
        # Shutdown telemetry (flush CloudEvents buffer)
        await shutdown_telemetry()


app = FastAPI(
    lifespan=lifespan,
    servers=[
        {"url": "https://api.honcho.dev", "description": "Production SaaS Platform"},
        {"url": "http://localhost:8000", "description": "Local Development Server"},
    ],
    title="Honcho API",
    summary="The Identity Layer for the Agentic World",
    description="""Honcho is a platform for giving agents user-centric memory and social cognition.""",
    version=HONCHO_VERSION,
    contact={
        "name": "Plastic Labs",
        "url": "https://honcho.dev",
        "email": "hello@plasticlabs.ai",
    },
    license_info={
        "name": "GNU Affero General Public License v3.0",
        "identifier": "AGPL-3.0-only",
        "url": "https://github.com/plastic-labs/honcho/blob/main/LICENSE",
    },
)

setup_dev_tools(service_name="honcho-api", app=app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


add_pagination(app)

app.include_router(workspaces.router, prefix="/v3")
app.include_router(peers.router, prefix="/v3")
app.include_router(sessions.router, prefix="/v3")
app.include_router(messages.router, prefix="/v3")
app.include_router(conclusions.router, prefix="/v3")
app.include_router(hypotheses.router, prefix="/v3")
app.include_router(predictions.router, prefix="/v3")
app.include_router(traces.router, prefix="/v3")
app.include_router(inductions.router, prefix="/v3")
app.include_router(keys.router, prefix="/v3")
app.include_router(webhooks.router, prefix="/v3")

# Prometheus metrics endpoint
app.add_route("/metrics", metrics_endpoint, methods=["GET"])


@app.get("/health")
async def health_check():
    """Return process liveness; dependency readiness is available at /readyz."""
    return {"status": "ok"}


@app.get("/readyz")
async def readiness_check() -> Response:
    """Read configured dependencies without exposing their addresses or errors.

    Cache readiness concerns configured Redis, even when normal cache operations
    have fallen back to memory. Disabled cache is reported explicitly. This does
    not probe schemas, model providers, workers or stored-memory compatibility.
    """
    cache_enabled = is_cache_enabled()
    checks = {
        "database": "not_checked",
        "cache": "not_checked" if cache_enabled else "disabled",
    }
    active_check = "database"
    redis_client = None

    async def probe() -> None:
        nonlocal active_check, redis_client
        # SELECT only: use the existing AUTOCOMMIT read engine, never a writer.
        async with read_engine.connect() as connection:
            result = await connection.execute(text("SELECT 1"))
            if result.scalar_one() != 1:
                raise ValueError("Unexpected database probe result")
        checks["database"] = "ok"
        if cache_enabled:
            active_check = "cache"
            parts = urlsplit(settings.CACHE.URL)
            # Remove the demonstrated Cashews-only option. Preserve Redis DB,
            # TLS and other transport options; unsupported options fail closed.
            query = urlencode(
                [
                    (key, value)
                    for key, value in parse_qsl(parts.query, keep_blank_values=True)
                    if key != "suppress"
                ]
            )
            redis_client = redis_asyncio.from_url(
                urlunsplit(parts._replace(query=query)),
                socket_connect_timeout=_READINESS_PROBE_SECONDS,
                socket_timeout=_READINESS_PROBE_SECONDS,
            )
            # Redis shares command stubs with its synchronous client; this
            # async client's PING always returns an awaitable.
            ping_result = redis_client.ping()  # pyright: ignore[reportUnknownMemberType]
            if await cast(Awaitable[bool], ping_result) is not True:
                raise ValueError("Unexpected cache probe result")
            checks["cache"] = "ok"

    try:
        await asyncio.wait_for(probe(), timeout=_READINESS_PROBE_SECONDS)
    except Exception:
        # Never log provider exception text: it can contain connection secrets.
        checks[active_check] = "unavailable"
    finally:
        if redis_client is not None:
            try:
                await asyncio.wait_for(
                    redis_client.aclose(), timeout=_READINESS_CLOSE_SECONDS
                )
            except Exception:
                checks["cache"] = "unavailable"

    ready = checks["database"] == "ok" and checks["cache"] in {"ok", "disabled"}
    return JSONResponse(
        status_code=200 if ready else 503,
        content={"status": "ready" if ready else "unavailable", "checks": checks},
        headers={"Cache-Control": "no-store"},
    )


# Global exception handlers
@app.exception_handler(HonchoException)
async def honcho_exception_handler(_request: Request, exc: HonchoException):
    """Handle all Honcho-specific exceptions."""
    logger.error(f"{exc.__class__.__name__}: {exc.detail}", exc_info=exc)

    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


@app.exception_handler(Exception)
async def global_exception_handler(_request: Request, exc: Exception):
    """Handle all unhandled exceptions."""
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)

    if SENTRY_ENABLED:
        sentry_sdk.capture_exception(exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected error occurred"},
    )


@app.middleware("http")
async def track_request(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
):
    # Create a request ID that includes endpoint information
    endpoint = re.sub(r"/[A-Za-z0-9_-]{21}", "", request.url.path).replace("/", "_")
    request_id = f"{request.method}:{endpoint}:{str(uuid.uuid4())[:8]}"

    # Store in request state and context var
    request.state.request_id = request_id
    token = request_context.set(f"api:{request_id}")

    try:
        response = await call_next(request)

        # Track metrics if enabled
        if settings.METRICS.ENABLED:
            template = get_route_template(request)
            prometheus_metrics.record_api_request(
                method=request.method,
                endpoint=template,
                status_code=str(response.status_code),
            )

        return response
    finally:
        request_context.reset(token)
