"""Match endpoint for Plex metadata matching."""

import logging
from json import JSONDecodeError

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from provider.models import (
    PlexMatchRequest,
    PlexMediaContainer,
    plex_page,
    plex_response,
)
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
    except (ValidationError, JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(400, "Invalid match request") from exc

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
    matches = await service.search(title, year=year, media_type=media_type, guid=body.guid)
    if not body.manual:
        matches = matches[:1]

    offset, page = plex_page(request, matches)

    response = plex_response(PlexMediaContainer(
        identifier="tv.plex.agents.custom.tpdb",
        offset=offset,
        size=len(page),
        totalSize=len(matches),
        Metadata=page,
    ))

    return JSONResponse(content=response)
