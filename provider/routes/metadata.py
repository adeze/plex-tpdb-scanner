"""Metadata endpoint for Plex metadata retrieval."""

import logging
from urllib.parse import urlparse

import httpx2
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from provider.services.metadata_service import get_metadata_service
from provider.mappers.tpdb_to_plex import extract_scene_images
from provider.models import PlexImage, PlexMediaContainer, PlexMetadata, plex_response

logger = logging.getLogger(__name__)

router = APIRouter()
_image_client: httpx2.AsyncClient | None = None


def get_image_client() -> httpx2.AsyncClient:
    global _image_client
    if _image_client is None:
        _image_client = httpx2.AsyncClient(
            timeout=httpx2.Timeout(60.0),
            headers={"User-Agent": "TPDB-Plex-Scanner/1.0", "Accept": "image/*"},
            http2=True,
        )
    return _image_client


async def close_image_client():
    if _image_client is not None:
        await _image_client.aclose()


@router.get("/library/metadata/person/{person_key}")
async def get_person_metadata(person_key: str):
    """Return a TPDB performer as Plex person metadata."""
    identifier = person_key.removeprefix("person/")
    if not identifier:
        raise HTTPException(status_code=400, detail="Invalid person identifier")

    metadata = await get_metadata_service().get_performer_metadata(identifier)
    if not metadata:
        raise HTTPException(status_code=404, detail="Performer not found")

    return JSONResponse(content=plex_response(PlexMediaContainer(
        identifier="tv.plex.agents.custom.tpdb",
        offset=0,
        totalSize=1,
        size=1,
        Metadata=[PlexMetadata.model_validate(metadata)],
    )))


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
    metadata = await service.get_metadata(rating_key)

    if not metadata:
        raise HTTPException(status_code=404, detail="Scene not found")

    return JSONResponse(content=plex_response(PlexMediaContainer(
        identifier="tv.plex.agents.custom.tpdb",
        offset=0,
        totalSize=1,
        size=1,
        Metadata=[PlexMetadata.model_validate(metadata)],
    )))


@router.get("/library/metadata/{rating_key}/images")
async def get_metadata_images(rating_key: str, request: Request):
    """
    Get image metadata entries for a scene.

    Args:
        rating_key: The TPDB scene slug

    Returns:
        MediaContainer with image metadata entries
    """
    logger.info("Metadata images request for: %s", rating_key)

    service = get_metadata_service()
    images = await service.get_images(rating_key)

    if images is None:
        raise HTTPException(status_code=404, detail="Scene not found")

    try:
        offset = max(int(request.headers.get("X-Plex-Container-Start", "0")), 0)
        requested_size = int(request.headers.get("X-Plex-Container-Size", "0"))
    except ValueError:
        offset = 0
        requested_size = 0
    page = images[offset:offset + requested_size] if requested_size > 0 else images[offset:]

    return JSONResponse(content=plex_response(PlexMediaContainer(
        identifier="tv.plex.agents.custom.tpdb",
        offset=offset,
        totalSize=len(images),
        size=len(page),
        Image=[PlexImage.model_validate(image) for image in page],
    )))


@router.get("/library/metadata/{rating_key}/extras")
async def get_metadata_extras(rating_key: str):
    """Return an empty extras collection for Plex metadata refreshes."""
    return JSONResponse(
        content={
            "MediaContainer": {
                "identifier": "tv.plex.agents.custom.tpdb",
                "offset": 0,
                "totalSize": 0,
                "size": 0,
            }
        }
    )


@router.api_route(
    "/library/metadata/{rating_key}/image/{image_type}/{image_index}",
    methods=["GET", "HEAD"],
)
async def get_image(rating_key: str, image_type: str, image_index: int):
    """Fetch one TPDB image on demand and return its bytes to Plex."""
    image_type = {"coverPoster": "poster", "background": "art"}.get(image_type, image_type)
    if image_type not in {"poster", "art"} or image_index < 0:
        raise HTTPException(status_code=400, detail="Invalid image selector")

    scene = await get_metadata_service().get_scene(rating_key)
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")

    images = [entry for entry in extract_scene_images(scene) if entry["type"] == image_type]
    if image_index >= len(images):
        raise HTTPException(status_code=404, detail="Image not found")

    image_url = images[image_index]["url"]
    logger.info(
        "event=image_fetch rating_key=%s image_type=%s image_index=%d",
        rating_key,
        image_type,
        image_index,
    )
    parsed = urlparse(image_url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise HTTPException(status_code=502, detail="Unsupported image URL")

    try:
        upstream = await get_image_client().get(image_url)
    except httpx2.HTTPError as exc:
        logger.warning("Failed to fetch image %s: %s", image_url, exc)
        raise HTTPException(status_code=502, detail="Image fetch failed") from exc

    if upstream.status_code != 200 or not upstream.content:
        logger.warning(
            "event=image_fetch_failed rating_key=%s status=%d",
            rating_key,
            upstream.status_code,
        )
        raise HTTPException(status_code=502, detail="Image fetch failed")

    content_type = upstream.headers.get("content-type", "image/jpeg").split(";", 1)[0]
    if not content_type.startswith("image/"):
        raise HTTPException(status_code=502, detail="Upstream response is not an image")

    return Response(
        content=upstream.content,
        media_type=content_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )
