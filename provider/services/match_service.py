"""Async and fuzzy matching service for TPDB scenes."""

import logging
import re
import sys
from pathlib import Path
from typing import Optional

from rapidfuzz import fuzz

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from provider.mappers.tpdb_to_plex import map_scene_to_match
from provider.services.metadata_service import MetadataService

logger = logging.getLogger(__name__)

_TECHNICAL_TOKENS = re.compile(
    r"\b(?:2160p|1440p|1080p|720p|4k|8k|hevc|h265|h264|av1|x264|x265|hdr|sdr|"
    r"fisheye\d*|lr|vr|180|360|3d|full[- ]?side[- ]?by[- ]?side|side[- ]?by[- ]?side)\b",
    re.IGNORECASE,
)


def normalize_match_text(value: str) -> str:
    """Normalize filenames and titles before searching and scoring."""
    value = _TECHNICAL_TOKENS.sub(" ", value or "")
    value = re.sub(r"[_./\\-]+", " ", value)
    value = re.sub(r"[^\w\s]", " ", value, flags=re.UNICODE)
    return re.sub(r"\s+", " ", value).strip().lower()


class MatchService(MetadataService):
    """Match Plex media against TPDB using normalized fuzzy scoring."""

    @staticmethod
    def _candidate_score(query: str, scene: dict, year: Optional[int]) -> int:
        query_text = normalize_match_text(query)
        title = normalize_match_text(str(scene.get("title", "")))
        site = scene.get("site") or scene.get("site_hydrated") or {}
        site_name = normalize_match_text(str(site.get("name", ""))) if isinstance(site, dict) else ""
        combined = normalize_match_text(f"{site_name} {title}")

        title_score = max(
            fuzz.WRatio(query_text, title),
            fuzz.WRatio(query_text, combined),
            fuzz.token_set_ratio(query_text, title),
        )

        performer_names = []
        for performer in scene.get("performers") or []:
            if isinstance(performer, dict):
                performer_names.append(str(performer.get("name", "")))
        performer_score = max(
            (fuzz.token_set_ratio(query_text, normalize_match_text(name)) for name in performer_names if name),
            default=0,
        )

        year_score = 0
        scene_date = str(scene.get("date", ""))
        if year and scene_date[:4].isdigit():
            difference = abs(year - int(scene_date[:4]))
            year_score = 10 if difference == 0 else 5 if difference == 1 else 0

        score = (title_score * 0.75) + (performer_score * 0.10) + year_score
        if site_name and site_name in query_text:
            score += 10
        return max(0, min(100, round(score)))

    async def search(self, title: str, year: Optional[int] = None, media_type: int = 1) -> list[dict]:
        logger.info("Searching for: %s (year=%s, type=%d)", title, year, media_type)
        normalized_title = normalize_match_text(title)
        results = await self.client.search_scenes(normalized_title, year=year)
        if not results and normalized_title != title:
            results = await self.client.search_scenes(title, year=year)

        if not results:
            logger.info("No results found for: %s", title)
            return []

        scored_results = []
        for scene in results:
            if not isinstance(scene, dict):
                continue
            try:
                # Match previews must stay fast. Full performer/site hydration
                # happens later when Plex requests selected-item metadata.
                score = self._candidate_score(title, scene, year)
                scored_results.append((score, scene))
            except Exception as exc:
                logger.warning("Failed to score scene %s: %s", scene.get("id"), exc)

        scored_results.sort(key=lambda item: item[0], reverse=True)
        matches = []
        for score, scene in scored_results:
            try:
                matches.append(map_scene_to_match(scene, score=score, media_type=media_type))
            except Exception as exc:
                logger.warning("Failed to map scene %s: %s", scene.get("id"), exc)
        logger.info("Found %d scored result(s) for: %s", len(matches), title)
        return matches


_match_service: Optional[MatchService] = None


def get_match_service() -> MatchService:
    global _match_service
    if _match_service is None:
        _match_service = MatchService()
    return _match_service


async def close_match_service():
    if _match_service is not None:
        await _match_service.close()
