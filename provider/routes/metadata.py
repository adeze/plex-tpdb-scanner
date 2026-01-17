"""Metadata endpoint for Plex metadata retrieval."""

import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from provider.services.metadata_service import get_metadata_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/library/metadata/{rating_key}")
async def get_metadata(rating_key: str):
    """
    Get full metadata for a scene.

    Args:
        rating_key: The TPDB scene slug

    Returns:
        MediaContainer with full metadata
    """
    logger.info("Metadata request for: %s", rating_key)

    service = get_metadata_service()
    metadata = service.get_metadata(rating_key)

    if not metadata:
        raise HTTPException(status_code=404, detail="Scene not found")

    response = {
        "MediaContainer": {
            "identifier": "tv.plex.agents.custom.tpdb",
            "offset": 0,
            "totalSize": 1,
            "size": 1,
            "Metadata": [metadata],
        }
    }

    return JSONResponse(content=response)
