"""Match service for searching TPDB scenes."""

import logging
import sys
from pathlib import Path
from typing import Optional

# Add parent directory to path to import metadata_tool
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from metadata_tool.api import TPDBClient

from provider.config import get_settings
from provider.mappers.tpdb_to_plex import map_scene_to_match

logger = logging.getLogger(__name__)


class MatchService:
    """Service for matching media to TPDB scenes."""

    def __init__(self):
        settings = get_settings()
        self.client = TPDBClient(settings.tpdb_api_key)
        self._performer_cache: dict[str, dict | None] = {}
        self._site_cache: dict[str, dict | None] = {}

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
        if performer_identifier not in self._performer_cache:
            self._performer_cache[performer_identifier] = self.client.get_performer(performer_identifier)
        return self._performer_cache[performer_identifier]

    def _get_cached_site(self, site_identifier: str) -> Optional[dict]:
        """Get site details with lightweight in-memory cache."""
        if not site_identifier:
            return None
        if site_identifier not in self._site_cache:
            self._site_cache[site_identifier] = self.client.get_site(site_identifier)
        return self._site_cache[site_identifier]

    def _hydrate_scene(self, scene: dict) -> dict:
        """Hydrate sparse scene payload with performer and site details."""
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

    def search(self, title: str, year: Optional[int] = None, media_type: int = 1) -> list[dict]:
        """
        Search for scenes matching the given title.

        Args:
            title: Search query (typically "Studio - Scene Title")
            year: Optional release year
            media_type: Plex media type (1=movie, 4=other videos)

        Returns:
            List of Plex-formatted match results
        """
        logger.info("Searching for: %s (year=%s, type=%d)", title, year, media_type)

        results = self.client.search_scenes(title, year=year)

        if not results:
            logger.info("No results found for: %s", title)
            return []

        logger.info("Found %d result(s) for: %s", len(results), title)

        matches = []
        for i, scene in enumerate(results):
            try:
                scene = self._hydrate_scene(scene)
                # Decrease score for each subsequent result
                score = max(100 - (i * 5), 50)
                match = map_scene_to_match(scene, score=score, media_type=media_type)
                matches.append(match)
            except Exception as e:
                logger.warning("Failed to map scene %s: %s", scene.get("id"), e)

        return matches


# Global service instance
_match_service: Optional[MatchService] = None


def get_match_service() -> MatchService:
    """Get or create the match service singleton."""
    global _match_service
    if _match_service is None:
        _match_service = MatchService()
    return _match_service
