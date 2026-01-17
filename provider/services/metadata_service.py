"""Metadata service for fetching full scene details from TPDB."""

import logging
import sys
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

    def __init__(self):
        settings = get_settings()
        self.client = TPDBClient(settings.tpdb_api_key)

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
