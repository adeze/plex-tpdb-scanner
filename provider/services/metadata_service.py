"""Async metadata service for fetching full scene details from TPDB."""

import asyncio
import logging
import sys
from collections import OrderedDict
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from metadata_tool.api import AsyncTPDBClient

from provider.config import get_settings
from provider.mappers.tpdb_to_plex import (
    map_performer_to_metadata,
    map_scene_to_images,
    map_scene_to_metadata,
)

logger = logging.getLogger(__name__)


class MetadataService:
    """Async service for fetching and hydrating TPDB scene metadata."""

    _CACHE_LIMIT = 512

    def __init__(self):
        settings = get_settings()
        self.client = AsyncTPDBClient(settings.tpdb_api_key)
        self._performer_cache: OrderedDict[str, dict | None] = OrderedDict()
        self._site_cache: OrderedDict[str, dict | None] = OrderedDict()

    @staticmethod
    def _first_identifier(payload: dict, keys: tuple[str, ...]) -> str:
        for key in keys:
            value = payload.get(key)
            if value is not None and value != "":
                return str(value)
        return ""

    @staticmethod
    def _has_image(payload: dict) -> bool:
        return any(payload.get(key) for key in ("image", "poster", "thumb", "photo", "avatar", "face"))

    async def _get_cached_performer(self, identifier: str) -> Optional[dict]:
        if not identifier:
            return None
        if identifier in self._performer_cache:
            self._performer_cache.move_to_end(identifier)
            logger.debug("event=cache_hit cache=performer key=%s", identifier)
        else:
            logger.info("event=cache_miss cache=performer key=%s", identifier)
            if len(self._performer_cache) >= self._CACHE_LIMIT:
                self._performer_cache.popitem(last=False)
            self._performer_cache[identifier] = await self.client.get_performer(identifier)
        return self._performer_cache[identifier]

    async def _get_cached_site(self, identifier: str) -> Optional[dict]:
        if not identifier:
            return None
        if identifier in self._site_cache:
            self._site_cache.move_to_end(identifier)
            logger.debug("event=cache_hit cache=site key=%s", identifier)
        else:
            logger.info("event=cache_miss cache=site key=%s", identifier)
            if len(self._site_cache) >= self._CACHE_LIMIT:
                self._site_cache.popitem(last=False)
            self._site_cache[identifier] = await self.client.get_site(identifier)
        return self._site_cache[identifier]

    async def _hydrate_scene(self, scene: dict) -> dict:
        """Hydrate sparse performer and site payloads without blocking I/O."""
        performers = scene.get("performers")
        if isinstance(performers, list):
            performer_tasks = {}
            for performer in performers:
                if not isinstance(performer, dict) or self._has_image(performer):
                    continue
                identifier = self._first_identifier(performer, ("id", "slug"))
                if identifier and identifier not in performer_tasks:
                    performer_tasks[identifier] = self._get_cached_performer(identifier)

            site = scene.get("site")
            site_identifier = self._first_identifier(site, ("id", "slug")) if isinstance(site, dict) else ""
            if not site_identifier:
                site_identifier = self._first_identifier(scene, ("site_id", "site_slug"))

            performer_ids = list(performer_tasks)
            hydration_results = await asyncio.gather(
                *performer_tasks.values(),
                self._get_cached_site(site_identifier),
            )
            performer_details = dict(zip(performer_ids, hydration_results[:-1]))
            hydrated_site = hydration_results[-1]

            hydrated_performers = []
            for performer in performers:
                if not isinstance(performer, dict) or self._has_image(performer):
                    hydrated_performers.append(performer)
                    continue
                identifier = self._first_identifier(performer, ("id", "slug"))
                details = performer_details.get(identifier)
                hydrated_performer = dict(details) if isinstance(details, dict) else {}
                hydrated_performer.update(performer)
                hydrated_performers.append(hydrated_performer)
            scene["performers"] = hydrated_performers
        else:
            site = scene.get("site")
            site_identifier = self._first_identifier(site, ("id", "slug")) if isinstance(site, dict) else ""
            if not site_identifier:
                site_identifier = self._first_identifier(scene, ("site_id", "site_slug"))
            hydrated_site = await self._get_cached_site(site_identifier)

        if isinstance(hydrated_site, dict):
            merged_site = dict(hydrated_site)
            if isinstance(site, dict):
                merged_site.update(site)
            scene["site_hydrated"] = hydrated_site
            scene["site"] = merged_site
        return scene

    async def get_scene(self, rating_key: str) -> Optional[dict]:
        scene = await self.client.get_scene(rating_key)
        if not scene:
            logger.warning("Scene not found: %s", rating_key)
            return None
        return await self._hydrate_scene(scene)

    async def get_metadata(self, rating_key: str) -> Optional[dict]:
        logger.info("Fetching metadata for: %s", rating_key)
        scene = await self.get_scene(rating_key)
        if not scene:
            return None
        logger.info("Found scene: %s", scene.get("title"))
        try:
            return map_scene_to_metadata(scene)
        except Exception as exc:
            logger.error("Failed to map scene %s: %s", rating_key, exc)
            return None

    async def get_images(self, rating_key: str) -> Optional[list[dict]]:
        logger.info("Fetching images for: %s", rating_key)
        scene = await self.get_scene(rating_key)
        if not scene:
            return None
        try:
            return map_scene_to_images(scene)
        except Exception as exc:
            logger.error("Failed to map images for scene %s: %s", rating_key, exc)
            return []

    async def get_performer_metadata(self, identifier: str) -> Optional[dict]:
        """Fetch and map one TPDB performer for Plex's person resource."""
        performer = await self._get_cached_performer(identifier)
        if not performer:
            logger.warning("Performer not found: %s", identifier)
            return None
        return map_performer_to_metadata(performer)

    async def close(self):
        await self.client.close()


_metadata_service: Optional[MetadataService] = None


def get_metadata_service() -> MetadataService:
    global _metadata_service
    if _metadata_service is None:
        _metadata_service = MetadataService()
    return _metadata_service


async def close_metadata_service():
    if _metadata_service is not None:
        await _metadata_service.close()
