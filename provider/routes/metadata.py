"""Metadata endpoint for Plex metadata retrieval."""

import logging
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, Response
import requests

from provider.services.metadata_service import get_metadata_service
from provider.mappers.tpdb_to_plex import extract_scene_images

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


@router.get("/library/metadata/{rating_key}/images")
async def get_metadata_images(rating_key: str):
    """
    Get image metadata entries for a scene.

    Args:
        rating_key: The TPDB scene slug

    Returns:
        MediaContainer with image metadata entries
    """
    logger.info("Metadata images request for: %s", rating_key)

    service = get_metadata_service()
    images = service.get_images(rating_key)

    if images is None:
        raise HTTPException(status_code=404, detail="Scene not found")

    response = {
        "MediaContainer": {
            "identifier": "tv.plex.agents.custom.tpdb",
            "offset": 0,
            "totalSize": len(images),
            "size": len(images),
            "Image": images,
        }
    }

    return JSONResponse(content=response)


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

    scene = get_metadata_service().get_scene(rating_key)
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")

    images = [entry for entry in extract_scene_images(scene) if entry["type"] == image_type]
    if image_index >= len(images):
        raise HTTPException(status_code=404, detail="Image not found")

    image_url = images[image_index]["url"]
    parsed = urlparse(image_url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise HTTPException(status_code=502, detail="Unsupported image URL")

    try:
        upstream = requests.get(
            image_url,
            headers={"User-Agent": "TPDB-Plex-Scanner/1.0", "Accept": "image/*"},
            timeout=60,
        )
    except requests.RequestException as exc:
        logger.warning("Failed to fetch image %s: %s", image_url, exc)
        raise HTTPException(status_code=502, detail="Image fetch failed") from exc

    if upstream.status_code != 200 or not upstream.content:
        raise HTTPException(status_code=502, detail="Image fetch failed")

    content_type = upstream.headers.get("content-type", "image/jpeg").split(";", 1)[0]
    if not content_type.startswith("image/"):
        raise HTTPException(status_code=502, detail="Upstream response is not an image")

    return Response(
        content=upstream.content,
        media_type=content_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )
