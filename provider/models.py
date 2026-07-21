"""Pydantic models for the Plex provider HTTP boundary."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PlexMatchRequest(BaseModel):
    """Subset of Plex's match request used by this provider."""

    model_config = ConfigDict(extra="ignore")

    type: int = 1
    title: str = ""
    year: int | None = None


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
