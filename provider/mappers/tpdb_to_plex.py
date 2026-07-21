"""Map TPDB scene data to Plex metadata format."""

import logging
from typing import Any
from urllib.parse import unquote

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


# Scores for poster slot: higher = better suited as a poster/thumb image.
# Screengrab/still/frame/gallery content is deprioritized with score 10.
_POSTER_KIND_SCORES: dict[str, int] = {
    "poster": 100,
    "cover": 90,
    "thumb": 70,
    "background": 30,
    "art": 30,
    "fanart": 30,
    "backdrop": 30,
    "screengrab": 10,
    "screenshot": 10,
    "still": 10,
    "frame": 10,
    "gallery": 10,
}

# Scores for art/background slot: higher = better suited as a background image.
_ART_KIND_SCORES: dict[str, int] = {
    "background": 100,
    "art": 100,
    "fanart": 100,
    "backdrop": 100,
    "poster": 30,
    "cover": 30,
    "thumb": 30,
    "screengrab": 10,
    "screenshot": 10,
    "still": 10,
    "frame": 10,
    "gallery": 10,
}

# Default score for unrecognized kinds (e.g. "image" or completely generic fields).
_GENERIC_SCORE = 50

# Candidates at or below this score are screengrab/still-like and are excluded
# from the extra image entries emitted by map_scene_to_images().
_SCREENGRAB_SCORE_THRESHOLD = 10


def _image_kind_from_key(key: str) -> str:
    """Map a field name or label string to a normalized image kind for scoring."""
    k = key.lower()
    if k in ("poster", "posters"):
        return "poster"
    if k in ("cover", "cover_image"):
        return "cover"
    if k in ("thumb", "thumbnail"):
        return "thumb"
    if k in ("background", "bg"):
        return "background"
    if k == "art":
        return "art"
    if k == "fanart":
        return "fanart"
    if k in ("backdrop", "backdrops"):
        return "backdrop"
    if k in ("screengrab", "screenshot", "screengrabs", "screenshots"):
        return "screengrab"
    if k in ("still", "stills", "frame", "frames"):
        return "still"
    if k in ("gallery", "galleries"):
        return "gallery"
    return "generic"


def _image_kind_from_url(url: str) -> str:
    """Infer an image kind from URL path/name hints when payload fields conflict."""
    value = unquote(url.lower())
    if any(token in value for token in ("screengrab", "screenshot", "screengrabs", "screenshots")):
        return "screengrab"
    if any(token in value for token in ("/still", "-still", "_still", "/frame", "-frame", "_frame")):
        return "still"
    if any(token in value for token in ("/background", "-background", "_background", "/backdrop")):
        return "background"
    if any(token in value for token in ("/fanart", "-fanart", "_fanart")):
        return "fanart"
    if any(token in value for token in ("/cover", "-cover", "_cover")):
        return "cover"
    return "generic"


def _classify_image(field_kind: str, url: str) -> str:
    """Combine payload field and URL hints, preferring explicit URL semantics."""
    url_kind = _image_kind_from_url(url)
    return url_kind if url_kind != "generic" else field_kind


def _image_source_score(url: str, kind: str) -> int:
    """Prefer canonical assets over transformed thumbnail proxies for art."""
    if kind in ("background", "art", "fanart", "backdrop"):
        value = url.lower()
        if "://thumb." in value or ".thumb." in value:
            return 10
        if "cdn.theporndb.net" in value:
            return 30
        return 20
    return 0


def _get_first_image(payload: dict[str, Any], fields: tuple[str, ...]) -> str:
    """Return the first non-empty image-like value from known fields."""
    for field in fields:
        if field in payload:
            image = _extract_string(payload.get(field))
            if image:
                return image
    return ""


# Top-level scene fields inspected for image candidates. _image_kind_from_key()
# is applied to each field name to derive the image kind (poster, background, etc.).
_SCENE_IMAGE_FIELDS: tuple[str, ...] = (
    "poster",
    "posters",
    "cover",
    "cover_image",
    "thumb",
    "background",
    "art",
    "fanart",
    "backdrop",
    "image",
)


def _collect_image_candidates(scene: dict[str, Any]) -> list[tuple[int, int, str]]:
    """Collect all image URL candidates from a scene payload with poster and art scores.

    Inspects top-level image fields and ``scene["images"]`` (dict or list).
    When ``images`` items carry type/category/name/label hints, those are used
    to classify the image so that screengrabs are deprioritised.

    Returns:
        List of ``(poster_score, art_score, source_score, url)`` tuples.
        Duplicate URLs are silently dropped.
    """
    seen_urls: set[str] = set()
    candidates: list[tuple[int, int, str]] = []

    def _add(url: str, kind: str) -> None:
        if url and url not in seen_urls:
            seen_urls.add(url)
            p = _POSTER_KIND_SCORES.get(kind, _GENERIC_SCORE)
            a = _ART_KIND_SCORES.get(kind, _GENERIC_SCORE)
            candidates.append((p, a, _image_source_score(url, kind), url))

    # Top-level named image fields
    for field in _SCENE_IMAGE_FIELDS:
        if field in scene:
            url = _extract_string(scene[field])
            _add(url, _classify_image(_image_kind_from_key(field), url))

    # scene["images"] — dict or list
    images = scene.get("images")
    if isinstance(images, dict):
        for key, value in images.items():
            url = _extract_string(value)
            _add(url, _image_kind_from_key(key))
    elif isinstance(images, list):
        for item in images:
            if isinstance(item, str):
                _add(item, "generic")
            elif isinstance(item, dict):
                # Determine kind from type/category/name/label hints when present.
                kind = "generic"
                for hint_key in ("type", "category", "name", "label", "kind"):
                    hint = item.get(hint_key)
                    if isinstance(hint, str):
                        k = _image_kind_from_key(hint)
                        if k != "generic":
                            kind = k
                            break
                url = _extract_string(item)
                _add(url, _classify_image(kind, url))

    return candidates


def _get_scene_poster(scene: dict[str, Any]) -> str:
    """Choose the best poster/thumb-like image from a scene payload.

    Scores all candidates and returns the URL with the highest poster score,
    so that promotional poster/cover assets are preferred over screengrabs.
    Falls back to any candidate when only generic or screengrab images exist.
    """
    candidates = _collect_image_candidates(scene)
    if not candidates:
        logger.debug(
            "No scene poster image extracted for scene=%s; available_keys=%s",
            scene.get("slug", scene.get("id", "")),
            sorted(scene.keys()),
        )
        return ""
    return max(candidates, key=lambda c: (c[0], c[2]))[3]


def _get_scene_art(scene: dict[str, Any]) -> str:
    """Choose the best background/art-like image from a scene payload.

    Scores all candidates and returns the URL with the highest art score,
    so that background/fanart assets are preferred over screengrabs.
    Falls back to any candidate when only generic or screengrab images exist.
    """
    candidates = _collect_image_candidates(scene)
    if not candidates:
        logger.debug(
            "No scene art image extracted for scene=%s; available_keys=%s",
            scene.get("slug", scene.get("id", "")),
            sorted(scene.keys()),
        )
        return ""
    return max(candidates, key=lambda c: (c[1], c[2]))[3]


def extract_scene_images(scene: dict[str, Any]) -> list[dict[str, str]]:
    """Extract Plex image slot entries from a scene payload.

    Returns a list of ``{"type": ..., "url": ...}`` dicts.  The primary poster
    (``type="poster"``) and primary art (``type="art"``) entries come first.
    Additional poster and art candidates with meaningful scores are appended so
    that Plex can present them as alternative selections in the image picker.
    Duplicate URLs are excluded.
    """
    candidates = _collect_image_candidates(scene)
    if not candidates:
        return []

    by_poster = sorted(candidates, key=lambda c: (c[0], c[2]), reverse=True)
    by_art = sorted(candidates, key=lambda c: (c[1], c[2]), reverse=True)

    entries: list[dict[str, str]] = []
    seen_urls: set[str] = set()

    # Best poster candidate
    best_poster_url = by_poster[0][3]
    entries.append({"type": "poster", "url": best_poster_url})
    seen_urls.add(best_poster_url)

    # Best art candidate (must be a different URL from the primary poster)
    for _, _, _, url in by_art:
        if url not in seen_urls:
            entries.append({"type": "art", "url": url})
            seen_urls.add(url)
            break

    # Additional poster candidates: distinct URLs with a meaningful poster score
    for poster_score, _, _, url in by_poster[1:]:
        if url not in seen_urls and poster_score > _SCREENGRAB_SCORE_THRESHOLD:
            entries.append({"type": "poster", "url": url})
            seen_urls.add(url)

    # Additional art candidates: distinct URLs with a meaningful art score
    for _, art_score, _, url in by_art:
        if url not in seen_urls and art_score > _SCREENGRAB_SCORE_THRESHOLD:
            entries.append({"type": "art", "url": url})
            seen_urls.add(url)

    return entries


def map_scene_to_images(scene: dict[str, Any]) -> list[dict[str, Any]]:
    """Map TPDB scene payload to Plex image metadata entries.

    Returns one entry per unique candidate URL.  The primary poster and art are
    first; additional candidates follow so Plex can offer them as alternatives.
    """
    slug = scene.get("slug", scene.get("id", ""))
    scene_images = extract_scene_images(scene)

    image_entries = []
    type_indices = {"poster": 0, "art": 0}
    seen_urls: set[str] = set()
    for entry in scene_images:
        image_type = entry["type"]
        image_url = entry["url"]
        if image_url in seen_urls:
            logger.debug(
                "Skipping duplicate image url for scene=%s type=%s url=%s",
                slug,
                image_type,
                image_url,
            )
            continue
        seen_urls.add(image_url)
        type_index = type_indices[image_type]
        type_indices[image_type] += 1
        plex_image_type = {"poster": "coverPoster", "art": "background"}[image_type]
        image_entries.append(
            {
                "type": plex_image_type,
                "url": image_url,
                "key": f"/library/metadata/{slug}/images/{plex_image_type}/{type_index}",
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
    studio = _get_studio(scene)
    if studio:
        candidates.append(studio)

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
        # Plex's match UI fetches this preview directly; keep it as the
        # canonical TPDB HTTPS asset rather than the on-demand provider proxy.
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

    match_result["isAdult"] = True

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
        # Plex metadata refreshes fetch the primary artwork directly, just as
        # the match preview does. Keep the proxy for on-demand image assets.
        metadata["thumb"] = poster

    if background:
        metadata["art"] = background

    # Expose the complete asset list on the metadata object. Plex uses these
    # entries to fetch and persist artwork during metadata refreshes.
    metadata["Image"] = map_scene_to_images(scene)

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

    metadata["isAdult"] = True

    guid_entries = _get_guid_entries(scene)
    if guid_entries:
        metadata["Guid"] = guid_entries

    return metadata
