"""Metadata service for fetching full scene details from TPDB."""

import logging
import sys
from collections import OrderedDict
from pathlib import Path
from typing import Optional

# Add parent directory to path to import metadata_tool
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from metadata_tool.api import TPDBClient

from provider.config import get_settings
from provider.mappers.tpdb_to_plex import map_scene_to_metadata

logger = logging.getLogger(__name__)


class MetadataService:
    """Service for fetching full metadata from TPDB."""

    _CACHE_LIMIT = 512

    def __init__(self):
        settings = get_settings()
        self.client = TPDBClient(settings.tpdb_api_key)
        self._performer_cache: OrderedDict[str, dict | None] = OrderedDict()
        self._site_cache: OrderedDict[str, dict | None] = OrderedDict()

    @staticmethod
    def _first_identifier(payload: dict, keys: tuple[str, ...]) -> str:
        """Get the first non-empty identifier from payload keys."""
        for key in keys:
            value = payload.get(key)
            if value is not None and value != "":
                return str(value)
        return ""

    @staticmethod
    def _has_image(payload: dict) -> bool:
        """Check if payload already includes any image-like field."""
        return any(payload.get(key) for key in ("image", "poster", "thumb", "photo", "avatar"))

    def _get_cached_performer(self, performer_identifier: str) -> Optional[dict]:
        """Get performer details with lightweight in-memory cache."""
        if not performer_identifier:
            return None
        if performer_identifier in self._performer_cache:
            self._performer_cache.move_to_end(performer_identifier)
        else:
            if len(self._performer_cache) >= self._CACHE_LIMIT:
                self._performer_cache.popitem(last=False)
            self._performer_cache[performer_identifier] = self.client.get_performer(performer_identifier)
        return self._performer_cache[performer_identifier]

    def _get_cached_site(self, site_identifier: str) -> Optional[dict]:
        """Get site details with lightweight in-memory cache."""
        if not site_identifier:
            return None
        if site_identifier in self._site_cache:
            self._site_cache.move_to_end(site_identifier)
        else:
            if len(self._site_cache) >= self._CACHE_LIMIT:
                self._site_cache.popitem(last=False)
            self._site_cache[site_identifier] = self.client.get_site(site_identifier)
        return self._site_cache[site_identifier]

    def _hydrate_scene(self, scene: dict) -> dict:
        """Hydrate sparse scene payload with performer and site details.

        Inline scene fields take precedence over hydrated fields when both exist.
        """
        performers = scene.get("performers")
        if isinstance(performers, list):
            hydrated_performers = []
            for performer in performers:
                if not isinstance(performer, dict):
                    hydrated_performers.append(performer)
                    continue
                hydrated_performer = performer
                if not self._has_image(performer):
                    performer_identifier = self._first_identifier(performer, ("id", "slug"))
                    details = self._get_cached_performer(performer_identifier)
                    if isinstance(details, dict):
                        hydrated_performer = dict(details)
                        hydrated_performer.update(performer)
                hydrated_performers.append(hydrated_performer)
            scene["performers"] = hydrated_performers

        site = scene.get("site")
        site_identifier = ""
        if isinstance(site, dict):
            site_identifier = self._first_identifier(site, ("id", "slug"))
        if not site_identifier:
            site_identifier = self._first_identifier(scene, ("site_id", "site_slug"))

        hydrated_site = self._get_cached_site(site_identifier)
        if isinstance(hydrated_site, dict):
            merged_site = dict(hydrated_site)
            if isinstance(site, dict):
                merged_site.update(site)
            scene["site_hydrated"] = hydrated_site
            scene["site"] = merged_site

        return scene

    def get_metadata(self, rating_key: str) -> Optional[dict]:
        """
        Get full metadata for a scene by its rating key (slug).

        Args:
            rating_key: TPDB scene slug

        Returns:
            Plex-formatted metadata or None if not found
        """
        logger.info("Fetching metadata for: %s", rating_key)

        scene = self.client.get_scene(rating_key)

        if not scene:
            logger.warning("Scene not found: %s", rating_key)
            return None

        scene = self._hydrate_scene(scene)

        logger.info("Found scene: %s", scene.get("title"))

        try:
            return map_scene_to_metadata(scene)
        except Exception as e:
            logger.error("Failed to map scene %s: %s", rating_key, e)
            return None


# Global service instance
_metadata_service: Optional[MetadataService] = None


def get_metadata_service() -> MetadataService:
    """Get or create the metadata service singleton."""
    global _metadata_service
    if _metadata_service is None:
        _metadata_service = MetadataService()
    return _metadata_service
