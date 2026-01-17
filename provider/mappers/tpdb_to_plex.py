"""Map TPDB scene data to Plex metadata format."""

from typing import Any


def map_scene_to_match(scene: dict[str, Any], score: int = 100) -> dict[str, Any]:
    """
    Map a TPDB scene to a Plex match result.

    Includes full metadata since Plex may not call the metadata endpoint for movies.

    Args:
        scene: TPDB scene data
        score: Match confidence score (0-100)

    Returns:
        Plex-formatted match result with full metadata
    """
    slug = scene.get("slug", scene.get("id", ""))
    title = scene.get("title", "")
    date = scene.get("date", "")
    year = int(date.split("-")[0]) if date and "-" in date else None
    summary = scene.get("description") or ""

    # Get poster image
    poster = scene.get("poster") or scene.get("image") or ""
    if isinstance(poster, dict):
        poster = poster.get("url", "")

    # Get background/fanart
    background = scene.get("background") or ""
    if isinstance(background, dict):
        background = background.get("url", "")

    # Get studio name
    site = scene.get("site") or {}
    studio = site.get("name", "") if isinstance(site, dict) else ""

    # Get duration in milliseconds
    duration = scene.get("duration")
    if duration:
        duration = int(duration) * 1000

    match_result = {
        "type": "movie",
        "guid": f"tv.plex.agents.custom.tpdb://movie/{slug}",
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

    # Map performers to roles
    performers = scene.get("performers") or []
    if performers:
        roles = []
        for performer in performers:
            if isinstance(performer, dict):
                role = {"tag": performer.get("name", "")}
                performer_image = performer.get("image") or performer.get("poster") or ""
                if isinstance(performer_image, dict):
                    performer_image = performer_image.get("url", "")
                if performer_image:
                    role["thumb"] = performer_image
                roles.append(role)
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

    return match_result


def map_scene_to_metadata(scene: dict[str, Any]) -> dict[str, Any]:
    """
    Map a TPDB scene to full Plex metadata.

    Args:
        scene: TPDB scene data

    Returns:
        Plex-formatted metadata
    """
    slug = scene.get("slug", scene.get("id", ""))
    title = scene.get("title", "")
    date = scene.get("date", "")
    year = int(date.split("-")[0]) if date and "-" in date else None
    summary = scene.get("description") or ""

    # Get poster image
    poster = scene.get("poster") or scene.get("image") or ""
    if isinstance(poster, dict):
        poster = poster.get("url", "")

    # Get background/fanart
    background = scene.get("background") or ""
    if isinstance(background, dict):
        background = background.get("url", "")

    # Get studio name
    site = scene.get("site") or {}
    studio = site.get("name", "") if isinstance(site, dict) else ""

    # Get duration in milliseconds
    duration = scene.get("duration")
    if duration:
        duration = int(duration) * 1000  # Integer milliseconds for Plex

    metadata = {
        "type": "movie",
        "guid": f"tv.plex.agents.custom.tpdb://movie/{slug}",
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

    # Map performers to roles
    performers = scene.get("performers") or []
    if performers:
        roles = []
        for performer in performers:
            if isinstance(performer, dict):
                role = {"tag": performer.get("name", "")}
                performer_image = performer.get("image") or performer.get("poster") or ""
                if isinstance(performer_image, dict):
                    performer_image = performer_image.get("url", "")
                if performer_image:
                    role["thumb"] = performer_image
                roles.append(role)
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

    return metadata
