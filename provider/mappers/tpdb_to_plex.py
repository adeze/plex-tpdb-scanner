"""Map TPDB scene data to Plex metadata format."""

import logging
from typing import Any

# Plex type mappings
PLEX_TYPE_MOVIE = 1
PLEX_TYPE_OTHER = 4

TYPE_STRINGS = {
    PLEX_TYPE_MOVIE: "movie",
    PLEX_TYPE_OTHER: "clip",
}

logger = logging.getLogger(__name__)


def _extract_string(value: Any, depth: int = 0, max_depth: int = 5) -> str:
    """Extract a useful string from scalar or nested payload values."""
    if depth > max_depth:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("url", "src", "path", "image", "poster", "thumb", "face", "full", "large"):
            nested = _extract_string(value.get(key), depth=depth + 1, max_depth=max_depth)
            if nested:
                return nested
    if isinstance(value, list):
        for item in value:
            nested = _extract_string(item, depth=depth + 1, max_depth=max_depth)
            if nested:
                return nested
    return ""


def _get_first_image(payload: dict[str, Any], fields: tuple[str, ...]) -> str:
    """Return the first non-empty image-like value from known fields."""
    for field in fields:
        if field in payload:
            image = _extract_string(payload.get(field))
            if image:
                return image
    return ""


def _get_scene_poster(scene: dict[str, Any]) -> str:
    """Choose the best poster/thumb-like image from a scene payload."""
    poster = _get_first_image(
        scene,
        ("poster", "posters", "cover", "cover_image", "thumb", "image", "background", "art"),
    )
    if poster:
        return poster
    images = scene.get("images")
    if isinstance(images, dict):
        return _get_first_image(
            images,
            ("poster", "cover", "cover_image", "thumb", "image", "background", "art"),
        )
    if isinstance(images, list):
        return _extract_string(images)
    logger.debug(
        "No scene poster image extracted for scene=%s; available_keys=%s",
        scene.get("slug", scene.get("id", "")),
        sorted(scene.keys()),
    )
    return ""


def _get_scene_art(scene: dict[str, Any]) -> str:
    """Choose the best background/art-like image from a scene payload."""
    background = _get_first_image(
        scene,
        ("background", "art", "fanart", "backdrop", "image", "poster", "thumb"),
    )
    if background:
        return background
    images = scene.get("images")
    if isinstance(images, dict):
        return _get_first_image(
            images,
            ("background", "art", "fanart", "backdrop", "image", "poster", "thumb"),
        )
    if isinstance(images, list):
        return _extract_string(images)
    logger.debug(
        "No scene art image extracted for scene=%s; available_keys=%s",
        scene.get("slug", scene.get("id", "")),
        sorted(scene.keys()),
    )
    return ""


def extract_scene_images(scene: dict[str, Any]) -> dict[str, str]:
    """Extract normalized Plex image slots from a scene payload."""
    images: dict[str, str] = {}

    poster = _get_scene_poster(scene)
    if poster:
        images["poster"] = poster
        images["thumb"] = poster

    art = _get_scene_art(scene)
    if art:
        images["art"] = art
        images["background"] = art

    return images


def map_scene_to_images(scene: dict[str, Any]) -> list[dict[str, Any]]:
    """Map TPDB scene payload to Plex image metadata entries."""
    slug = scene.get("slug", scene.get("id", ""))
    scene_images = extract_scene_images(scene)

    image_entries = []
    seen_urls: set[str] = set()
    for image_type, image_url in scene_images.items():
        if image_url in seen_urls:
            logger.debug(
                "Skipping duplicate image url for scene=%s type=%s url=%s",
                slug,
                image_type,
                image_url,
            )
            continue
        seen_urls.add(image_url)
        image_entries.append(
            {
                "type": image_type,
                "url": image_url,
                "key": f"/library/metadata/{slug}/images/{image_type}",
                "ratingKey": slug,
                "provider": "tv.plex.agents.custom.tpdb",
            }
        )

    return image_entries


def _normalize_people(items: Any) -> list[dict[str, str]]:
    """Normalize person payloads to Plex person format."""
    if isinstance(items, dict):
        items = [items]
    if not isinstance(items, list):
        return []

    people = []
    for item in items:
        if isinstance(item, dict):
            name = item.get("name") or item.get("title") or item.get("tag")
        elif isinstance(item, str):
            name = item
        else:
            name = ""
        if isinstance(name, str) and name:
            people.append({"tag": name})
    return people


def _get_collections(scene: dict[str, Any]) -> list[dict[str, str]]:
    """Extract collection/series/franchise names from scene payloads."""
    candidates = []
    for key in ("collections", "collection", "series", "franchise", "franchises"):
        if key in scene:
            value = scene.get(key)
            if isinstance(value, list):
                candidates.extend(value)
            else:
                candidates.append(value)

    collections: list[dict[str, str]] = []
    seen: set[str] = set()
    for value in candidates:
        if isinstance(value, dict):
            name = value.get("name") or value.get("title") or value.get("tag")
        elif isinstance(value, str):
            name = value
        else:
            name = ""
        if isinstance(name, str) and name and name not in seen:
            collections.append({"tag": name})
            seen.add(name)
    return collections


def _get_studio(scene: dict[str, Any]) -> str:
    """Extract normalized studio/site name from scene payload."""
    site = scene.get("site") or scene.get("site_hydrated") or {}
    if isinstance(site, dict):
        return site.get("name") or site.get("title") or ""
    return ""


def _extract_provider_id(payload: dict[str, Any], keys: tuple[str, ...]) -> str:
    """Extract first non-empty provider ID from known key names."""
    for key in keys:
        value = payload.get(key)
        if value is not None and value != "":
            return str(value)
    return ""


def _get_guid_entries(scene: dict[str, Any]) -> list[dict[str, str]]:
    """Build Plex Guid entries for TPDB and known external providers."""
    external_sources: list[dict[str, Any]] = [scene]
    for key in ("ids", "external_ids"):
        candidate = scene.get(key)
        if isinstance(candidate, dict):
            external_sources.append(candidate)

    provider_keys = {
        "imdb": ("imdb", "imdb_id"),
        "tmdb": ("tmdb", "tmdb_id"),
        "tvdb": ("tvdb", "tvdb_id"),
    }

    guid_ids: list[str] = []
    for provider, keys in provider_keys.items():
        for source in external_sources:
            provider_id = _extract_provider_id(source, keys)
            if provider_id:
                guid_ids.append(f"{provider}://{provider_id}")
                break

    tpdb_identifier = _extract_provider_id(scene, ("id", "slug"))
    if tpdb_identifier:
        guid_ids.append(f"tpdb://{tpdb_identifier}")

    return [{"id": guid_id} for guid_id in dict.fromkeys(guid_ids)]


def _map_roles(performers: Any) -> list[dict[str, str]]:
    """Map TPDB performers to Plex Role entries."""
    if not isinstance(performers, list):
        return []

    roles: list[dict[str, str]] = []
    for performer in performers:
        if not isinstance(performer, dict):
            continue
        role = {"tag": performer.get("name", "")}
        performer_id = _extract_provider_id(performer, ("id", "slug"))
        if performer_id:
            role["id"] = f"tpdb://performer/{performer_id}"
        performer_image = _get_first_image(
            performer,
            ("image", "poster", "thumb", "photo", "avatar", "face"),
        )
        if performer_image:
            role["thumb"] = performer_image
        roles.append(role)

    return roles


def map_scene_to_match(scene: dict[str, Any], score: int = 100, media_type: int = 1) -> dict[str, Any]:
    """
    Map a TPDB scene to a Plex match result.

    Includes full metadata since Plex may not call the metadata endpoint for movies.

    Args:
        scene: TPDB scene data
        score: Match confidence score (0-100)
        media_type: Plex media type (1=movie, 4=other videos)

    Returns:
        Plex-formatted match result with full metadata
    """
    slug = scene.get("slug", scene.get("id", ""))
    title = scene.get("title", "")
    date = scene.get("date", "")
    year = int(date.split("-")[0]) if date and "-" in date else None
    summary = scene.get("description") or ""

    poster = _get_scene_poster(scene)
    background = _get_scene_art(scene)
    studio = _get_studio(scene)

    # Get duration in milliseconds
    duration = scene.get("duration")
    if duration:
        duration = int(duration) * 1000

    type_str = TYPE_STRINGS.get(media_type, "movie")
    match_result = {
        "type": type_str,
        "guid": f"tv.plex.agents.custom.tpdb://{type_str}/{slug}",
        "key": f"/library/metadata/{slug}",
        "ratingKey": slug,
        "title": title,
        "name": title,  # Plex may use 'name' for match display
        "score": score,
    }

    if year:
        match_result["year"] = year

    if poster:
        match_result["thumb"] = poster

    if background:
        match_result["art"] = background

    if studio:
        match_result["studio"] = studio

    if date:
        match_result["originallyAvailableAt"] = date

    if summary:
        match_result["summary"] = summary

    if duration:
        match_result["duration"] = duration

    roles = _map_roles(scene.get("performers") or [])
    if roles:
        match_result["Role"] = roles

    # Map tags to genres
    tags = scene.get("tags") or []
    if tags:
        genres = []
        for tag in tags:
            if isinstance(tag, dict):
                tag_name = tag.get("name") or tag.get("tag", "")
            else:
                tag_name = str(tag)
            if tag_name:
                genres.append({"tag": tag_name})
        if genres:
            match_result["Genre"] = genres

    directors = _normalize_people(scene.get("directors") or scene.get("director"))
    if directors:
        match_result["Director"] = directors

    collections = _get_collections(scene)
    if collections:
        match_result["Collection"] = collections

    match_result["isAdult"] = 1

    guid_entries = _get_guid_entries(scene)
    if guid_entries:
        match_result["Guid"] = guid_entries

    return match_result


def map_scene_to_metadata(scene: dict[str, Any], media_type: int = 1) -> dict[str, Any]:
    """
    Map a TPDB scene to full Plex metadata.

    Args:
        scene: TPDB scene data
        media_type: Plex media type (1=movie, 4=other videos)

    Returns:
        Plex-formatted metadata
    """
    slug = scene.get("slug", scene.get("id", ""))
    title = scene.get("title", "")
    date = scene.get("date", "")
    year = int(date.split("-")[0]) if date and "-" in date else None
    summary = scene.get("description") or ""

    poster = _get_scene_poster(scene)
    background = _get_scene_art(scene)
    studio = _get_studio(scene)

    # Get duration in milliseconds
    duration = scene.get("duration")
    if duration:
        duration = int(duration) * 1000  # Integer milliseconds for Plex

    type_str = TYPE_STRINGS.get(media_type, "movie")
    metadata = {
        "type": type_str,
        "guid": f"tv.plex.agents.custom.tpdb://{type_str}/{slug}",
        "key": f"/library/metadata/{slug}",
        "ratingKey": slug,
        "title": title,
        "summary": summary,
    }

    if year:
        metadata["year"] = year  # Integer for Plex

    if date:
        metadata["originallyAvailableAt"] = date

    if poster:
        metadata["thumb"] = poster

    if background:
        metadata["art"] = background

    if studio:
        metadata["studio"] = studio

    if duration:
        metadata["duration"] = duration

    roles = _map_roles(scene.get("performers") or [])
    if roles:
        metadata["Role"] = roles

    # Map tags to genres
    tags = scene.get("tags") or []
    if tags:
        genres = []
        for tag in tags:
            if isinstance(tag, dict):
                tag_name = tag.get("name") or tag.get("tag", "")
            else:
                tag_name = str(tag)
            if tag_name:
                genres.append({"tag": tag_name})
        if genres:
            metadata["Genre"] = genres

    directors = _normalize_people(scene.get("directors") or scene.get("director"))
    if directors:
        metadata["Director"] = directors

    collections = _get_collections(scene)
    if collections:
        metadata["Collection"] = collections

    metadata["isAdult"] = 1

    guid_entries = _get_guid_entries(scene)
    if guid_entries:
        metadata["Guid"] = guid_entries

    return metadata
