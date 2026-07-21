"""Match endpoint for Plex metadata matching."""

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from provider.models import PlexMatchRequest, PlexMediaContainer, plex_response
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
        body = PlexMatchRequest.model_validate(await request.json())
    except Exception as exc:
        logger.error("Failed to parse request body: %s", exc)
        return JSONResponse(
            content=plex_response(PlexMediaContainer(identifier="tv.plex.agents.custom.tpdb")),
            status_code=200,
        )

    logger.debug("Match request: %s", body.model_dump())
    title = body.title
    year = body.year
    media_type = body.type

    if not title:
        return JSONResponse(
            content=plex_response(PlexMediaContainer(identifier="tv.plex.agents.custom.tpdb")),
            status_code=200,
        )

    # Handle movie type (1) and clip type (12).
    if media_type not in (1, 12):
        logger.warning("Unsupported media type: %s", media_type)
        return JSONResponse(
            content=plex_response(PlexMediaContainer(identifier="tv.plex.agents.custom.tpdb")),
            status_code=200,
        )

    service = get_match_service()
    matches = await service.search(title, year=year, media_type=media_type)

    try:
        offset = max(int(request.headers.get("X-Plex-Container-Start", "0")), 0)
        requested_size = int(request.headers.get("X-Plex-Container-Size", "0"))
    except ValueError:
        offset = 0
        requested_size = 0
    page = matches[offset:offset + requested_size] if requested_size > 0 else matches[offset:]

    response = plex_response(PlexMediaContainer(
        identifier="tv.plex.agents.custom.tpdb",
        offset=offset,
        size=len(page),
        totalSize=len(matches),
        Metadata=page,
    ))

    return JSONResponse(content=response)
