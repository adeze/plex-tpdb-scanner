"""TPDB Plex Metadata Provider - FastAPI Application."""

import logging
import sys
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from provider.config import get_settings
from provider.routes import manifest, matches, metadata
from provider.routes.metadata import close_image_client
from provider.services.match_service import close_match_service
from provider.services.metadata_service import close_metadata_service

# Configure logging
settings = get_settings()
logging.basicConfig(
    level=getattr(logging, settings.tpdb_log_level.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
# Our application middleware emits the useful request summary. Keep transport
# libraries quiet unless the configured application log level is DEBUG.
logging.getLogger("httpx2").setLevel(logging.WARNING)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    logger.info("TPDB Metadata Provider starting on port %d", settings.tpdb_port)
    try:
        yield
    finally:
        await close_image_client()
        await close_match_service()
        await close_metadata_service()
        logger.info("TPDB Metadata Provider shutting down")


app = FastAPI(
    title="TPDB Plex Metadata Provider",
    description="Plex Metadata Provider for ThePornDB",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health")
async def healthcheck():
    """Return a lightweight liveness response for Docker and Compose."""
    return {"status": "ok"}

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log one correlated, timed summary for every Plex request."""
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        duration_ms = (time.perf_counter() - started) * 1000
        logger.exception(
            "event=http_request method=%s path=%s status=500 duration_ms=%.1f",
            request.method,
            request.url.path,
            duration_ms,
        )
        raise

    duration_ms = (time.perf_counter() - started) * 1000
    logger.info(
        "event=http_request method=%s path=%s status=%d duration_ms=%.1f",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response


# Include routers
app.include_router(manifest.router)
app.include_router(matches.router)
app.include_router(metadata.router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "provider.main:app",
        host="0.0.0.0",
        port=settings.tpdb_port,
        reload=False,
    )
