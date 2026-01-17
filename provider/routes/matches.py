"""Match endpoint for Plex metadata matching."""

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from provider.services.match_service import get_match_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/library/metadata/matches")
async def match_media(request: Request):
    """
    Handle Plex match requests.

    Plex sends: {"type": 1, "title": "...", "year": 2024, "manual": 0}
    We return: {"MediaContainer": {"Metadata": [...]}}
    """
    try:
        body = await request.json()
    except Exception as e:
        logger.error("Failed to parse request body: %s", e)
        return JSONResponse(
            content={"MediaContainer": {"Metadata": []}},
            status_code=200,
        )

    logger.debug("Match request: %s", body)

    title = body.get("title", "")
    year = body.get("year")
    media_type = body.get("type", 1)

    if not title:
        return JSONResponse(
            content={"MediaContainer": {"Metadata": []}},
            status_code=200,
        )

    # Handle movie type (1) and other videos type (4)
    if media_type not in (1, 4):
        logger.warning("Unsupported media type: %s", media_type)
        return JSONResponse(
            content={"MediaContainer": {"Metadata": []}},
            status_code=200,
        )

    service = get_match_service()
    matches = service.search(title, year=year, media_type=media_type)

    response = {
        "MediaContainer": {
            "identifier": "tv.plex.agents.custom.tpdb",
            "size": len(matches),
            "Metadata": matches,
        }
    }

    return JSONResponse(content=response)
