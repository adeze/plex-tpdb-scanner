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
