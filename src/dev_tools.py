"""
Dev Tools Integration Module for Python Services
Adds Jaeger tracing, Loki logging, and Vault secrets to FastAPI/Starlette apps.

Usage in main.py:
    from src.dev_tools import setup_dev_tools, setup_dev_tools_logger
    
    # In lifespan startup:
    setup_dev_tools("honcho-api")
    logger = setup_dev_tools_logger("honcho-api")
"""

import os
import logging
from typing import Optional
import sys

# ============================================================================
# JAEGER TRACING SETUP
# ============================================================================

def setup_jaeger_tracing(service_name: str) -> Optional[object]:
    """
    Initialize OpenTelemetry with Jaeger exporter for distributed tracing.
    
    Args:
        service_name: Name of the service (e.g., "honcho-api")
    
    Returns:
        TracerProvider or None if disabled/unavailable
    """
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
        from opentelemetry.instrumentation.redis import RedisInstrumentor
        from opentelemetry.instrumentation.requests import RequestsInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        # Check if Jaeger/OTLP tracing is enabled
        if os.getenv("JAEGER_ENABLED", "true").lower() == "false":
            logging.info("Jaeger tracing disabled")
            return None

        otlp_endpoint = os.getenv(
            "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
            os.getenv(
                "OTEL_EXPORTER_OTLP_ENDPOINT",
                "http://jaeger:4318/v1/traces",
            ),
        )

        resource = Resource.create(
            {
                "service.name": service_name,
                "deployment.environment": os.getenv("ENVIRONMENT", "dev"),
            }
        )
        otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
        trace_provider = TracerProvider(resource=resource)
        trace_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
        trace.set_tracer_provider(trace_provider)

        # Instrument libraries (idempotent if already instrumented)
        FastAPIInstrumentor().instrument()
        SQLAlchemyInstrumentor().instrument()
        RedisInstrumentor().instrument()
        RequestsInstrumentor().instrument()
        HTTPXClientInstrumentor().instrument()

        logging.info("✓ OTLP tracing initialized for Jaeger: %s", otlp_endpoint)
        return trace_provider
        
    except ImportError as e:
        logging.warning(f"Jaeger libraries not installed: {e}. Run: pip install -r dev-tools-requirements.txt")
        return None
    except Exception as e:
        logging.error(f"Failed to initialize Jaeger: {e}")
        return None


# ============================================================================
# LOKI LOGGING SETUP
# ============================================================================

def setup_loki_logging(service_name: str, labels: Optional[dict] = None) -> logging.Logger:
    """
    Initialize Loki logger for centralized log aggregation.
    
    Args:
        service_name: Name of the service
        labels: Additional labels for log identification
    
    Returns:
        Configured logger instance
    """
    if labels is None:
        labels = {}
    
    labels["service"] = service_name
    labels["environment"] = os.getenv("ENVIRONMENT", "dev")
    
    try:
        from logging_loki import LokiHandler
        from pythonjsonlogger import jsonlogger
        
        # Check if Loki is enabled
        if os.getenv("LOKI_ENABLED", "true").lower() == "false":
            logging.basicConfig(level=logging.INFO)
            return logging.getLogger()
        
        loki_url = os.getenv("LOKI_URL", "http://localhost:3100")
        
        # Get root logger
        logger = logging.getLogger()
        logger.setLevel(logging.INFO)
        
        # Add Loki handler
        loki_handler = LokiHandler(
            url=f"{loki_url}/loki/api/v1/push",
            tags=labels,
            auth=("", ""),
            version="1",
        )
        
        # Set JSON formatter for structured logging
        formatter = jsonlogger.JsonFormatter(
            '%(asctime)s %(name)s %(levelname)s %(message)s'
        )
        loki_handler.setFormatter(formatter)
        logger.addHandler(loki_handler)
        
        # Also keep console handler for local development
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ))
        logger.addHandler(console_handler)
        
        logging.info(f"✓ Loki logging initialized: {loki_url}")
        return logger
        
    except ImportError as e:
        logging.warning(f"Loki libraries not installed: {e}. Run: pip install -r dev-tools-requirements.txt")
        logging.basicConfig(level=logging.INFO)
        return logging.getLogger()
    except Exception as e:
        logging.error(f"Failed to initialize Loki: {e}")
        logging.basicConfig(level=logging.INFO)
        return logging.getLogger()


# ============================================================================
# VAULT SECRET MANAGEMENT
# ============================================================================

class VaultClient:
    """Wrapper around hvac.Client with convenient methods for dev tools."""
    
    def __init__(self):
        try:
            import hvac
            
            vault_addr = os.getenv("VAULT_ADDR", "http://localhost:8200")
            vault_token = os.getenv("VAULT_TOKEN", "dev-token")
            
            self.client = hvac.Client(url=vault_addr, token=vault_token)
            
            # Test connection
            try:
                self.client.sys.read_health_status()
                logging.info(f"✓ Vault initialized: {vault_addr}")
            except Exception as e:
                logging.warning(f"Vault connection failed: {e}. Secrets will not be available.")
                self.client = None
                
        except ImportError:
            logging.warning("Hvac library not installed. Run: pip install -r dev-tools-requirements.txt")
            self.client = None
    
    def read_secret(self, path: str, key: Optional[str] = None) -> any:
        """Read secret from Vault KV v2 store."""
        if not self.client:
            logging.warning(f"Vault unavailable, cannot read {path}")
            return None
        
        try:
            secret = self.client.secrets.kv.v2.read_secret_version(path=path)
            data = secret["data"]["data"]
            return data.get(key) if key else data
        except Exception as e:
            logging.error(f"Failed to read secret {path}: {e}")
            return None
    
    def write_secret(self, path: str, secret_dict: dict) -> bool:
        """Write secret to Vault KV v2 store."""
        if not self.client:
            logging.warning(f"Vault unavailable, cannot write {path}")
            return False
        
        try:
            self.client.secrets.kv.v2.create_or_update_secret_version(
                path=path,
                secret_dict=secret_dict,
            )
            logging.info(f"✓ Secret written to {path}")
            return True
        except Exception as e:
            logging.error(f"Failed to write secret {path}: {e}")
            return False


def setup_vault() -> Optional[VaultClient]:
    """Initialize Vault client."""
    if os.getenv("VAULT_ENABLED", "true").lower() == "false":
        logging.info("Vault disabled")
        return None
    
    return VaultClient()


# ============================================================================
# FASTAPI MIDDLEWARE
# ============================================================================

def add_dev_tools_middleware(app) -> None:
    """Add request tracking middleware to FastAPI app."""
    from fastapi import Request
    import time
    
    @app.middleware("http")
    async def add_tracing_headers(request: Request, call_next):
        """Add tracing context and timing to requests."""
        start_time = time.time()
        
        # Extract or create trace ID
        trace_id = request.headers.get("X-Trace-ID", request.headers.get("X-Request-ID", ""))
        
        response = await call_next(request)
        
        process_time = time.time() - start_time
        response.headers["X-Process-Time"] = str(process_time)
        
        # Log request
        logging.info(
            "HTTP request completed",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": process_time * 1000,
                "trace_id": trace_id,
            }
        )
        
        return response


# ============================================================================
# COMPLETE SETUP
# ============================================================================

def setup_dev_tools(app=None, service_name: str = "service") -> dict:
    """
    Initialize all dev tools: Jaeger, Loki, Vault.
    
    Args:
        app: FastAPI app instance (optional)
        service_name: Service name for tracing/logging
    
    Returns:
        Dict with initialized components
    """
    components = {
        "tracer": setup_jaeger_tracing(service_name),
        "logger": setup_loki_logging(service_name),
        "vault": setup_vault(),
    }
    
    if app:
        add_dev_tools_middleware(app)
    
    return components


# ============================================================================
# USAGE EXAMPLES
# ============================================================================

"""
In your FastAPI main.py:

from src.dev_tools import setup_dev_tools

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize dev tools
    dev_tools = setup_dev_tools(app, "honcho-api")
    
    # Use vault to read secrets
    vault = dev_tools["vault"]
    if vault:
        db_password = vault.read_secret("honcho/db", "password")
        # Use in connection string
    
    yield
    
    # Cleanup happens automatically

# Create app with dev tools
app = FastAPI(lifespan=lifespan)
setup_dev_tools(app, "honcho-api")

# Now every request is:
# - Traced in Jaeger (see http://127.0.0.1:16686)
# - Logged to Loki (query in Grafana with {service="honcho-api"})
# - Can access secrets from Vault
"""
