"""TPDB Plex Metadata Provider - FastAPI Application."""

import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from provider.config import get_settings
from provider.routes import manifest, matches, metadata

# Configure logging
settings = get_settings()
logging.basicConfig(
    level=getattr(logging, settings.tpdb_log_level.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    logger.info("TPDB Metadata Provider starting on port %d", settings.tpdb_port)
    yield
    logger.info("TPDB Metadata Provider shutting down")


app = FastAPI(
    title="TPDB Plex Metadata Provider",
    description="Plex Metadata Provider for ThePornDB",
    version="1.0.0",
    lifespan=lifespan,
)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all incoming requests."""
    logger.info(">>> REQUEST: %s %s", request.method, request.url.path)
    response = await call_next(request)
    logger.info("<<< RESPONSE: %s %s -> %d", request.method, request.url.path, response.status_code)
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
