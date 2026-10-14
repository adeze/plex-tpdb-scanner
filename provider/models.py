"""Pydantic models for the Plex provider HTTP boundary."""

from typing import Any

from fastapi import HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field


class PlexMatchRequest(BaseModel):
    """Subset of Plex's match request used by this provider."""

    model_config = ConfigDict(extra="ignore")

    type: int
    title: str = Field(min_length=1)
    year: int | None = None
    manual: int = Field(default=0, ge=0, le=1)
    guid: str | None = None


def plex_page(request: Request, items: list) -> tuple[int, list]:
    """Read Plex pagination from headers or query parameters."""
    def value(name: str) -> int:
        raw = request.headers.get(name)
        if raw is None:
            raw = request.query_params.get(name, "0")
        try:
            number = int(raw)
        except (ValueError, TypeError) as exc:
            raise HTTPException(400, "Invalid pagination") from exc
        if number < 0:
            raise HTTPException(400, "Invalid pagination")
        return number

    offset = value("X-Plex-Container-Start")
    size = value("X-Plex-Container-Size")
    return offset, items[offset:offset + size] if size else items[offset:]


class PlexImage(BaseModel):
    """Canonical Plex image asset."""

    model_config = ConfigDict(extra="allow")

    type: str
    url: str
    key: str | None = None
    ratingKey: str | None = None
    provider: str | None = None


class PlexMetadata(BaseModel):
    """Flexible Plex metadata item with validated image assets."""

    model_config = ConfigDict(extra="allow")

    type: str | None = None
    ratingKey: str | None = None
    Image: list[PlexImage] | None = None


class PlexMediaContainer(BaseModel):
    """Flexible Plex response envelope with validated image assets."""

    model_config = ConfigDict(extra="allow")

    identifier: str
    offset: int = 0
    totalSize: int = 0
    size: int = 0
    Metadata: list[PlexMetadata] | None = None
    Image: list[PlexImage] | None = None


class PlexResponse(BaseModel):
    """Top-level Plex response object."""

    MediaContainer: PlexMediaContainer


def plex_response(container: PlexMediaContainer) -> dict[str, Any]:
    """Serialize a validated Plex response for FastAPI."""
    return PlexResponse(MediaContainer=container).model_dump(
        mode="json",
        exclude_none=True,
        by_alias=True,
    )
