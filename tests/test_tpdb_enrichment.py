import unittest
from collections import OrderedDict
from unittest.mock import AsyncMock, Mock

from provider.mappers.tpdb_to_plex import (
    extract_scene_images,
    map_scene_to_images,
    map_scene_to_match,
    map_scene_to_metadata,
)
from provider.services.metadata_service import MetadataService


class MapperEnrichmentTests(unittest.TestCase):
    def test_metadata_uses_image_fallback_director_and_collection(self):
        scene = {
            "id": "123",
            "title": "Scene",
            "description": "desc",
            "image": {"url": "https://img/poster.jpg"},
            "art": "https://img/art.jpg",
            "site": {"name": "Studio"},
            "performers": [{"id": "p1", "name": "Performer", "thumb": "https://img/p.jpg"}],
            "directors": [{"name": "Director One"}, {"name": "Director Two"}],
            "series": [{"name": "Series A"}],
            "franchise": "Franchise B",
            "imdb_id": "tt1234567",
            "ids": {"tmdb": "98765"},
        }

        metadata = map_scene_to_metadata(scene)

        self.assertEqual(metadata.get("thumb"), "https://img/poster.jpg")
        self.assertEqual(metadata.get("art"), "https://img/art.jpg")
        self.assertEqual(metadata.get("Director"), [{"tag": "Director One"}, {"tag": "Director Two"}])
        self.assertEqual(
            metadata.get("Collection"),
            [{"tag": "Series A"}, {"tag": "Franchise B"}, {"tag": "Studio"}],
        )
        self.assertEqual(
            metadata.get("Role"),
            [{"tag": "Performer", "id": "tv.plex.agents.custom.tpdb://person/p1", "key": "/library/metadata/person/p1", "url": "https://theporndb.net/performers/p1", "thumb": "https://img/p.jpg"}],
        )
        self.assertIs(metadata.get("isAdult"), True)
        self.assertEqual(
            metadata.get("Guid"),
            [{"id": "imdb://tt1234567"}, {"id": "tmdb://98765"}, {"id": "tpdb://123"}],
        )

    def test_match_supports_nested_images(self):
        scene = {
            "id": "123",
            "title": "Scene",
            "images": {
                "poster": {"src": "https://img/poster.jpg"},
                "background": {"url": "https://img/bg.jpg"},
            },
            "external_ids": {"tvdb_id": "321"},
        }

        match = map_scene_to_match(scene)

        self.assertEqual(match.get("thumb"), "https://img/poster.jpg")
        self.assertEqual(match.get("art"), "https://img/bg.jpg")
        self.assertIs(match.get("isAdult"), True)
        self.assertEqual(match.get("Guid"), [{"id": "tvdb://321"}, {"id": "tpdb://123"}])

    def test_studio_added_to_match_collection_without_duplicates(self):
        scene = {
            "id": "123",
            "title": "Scene",
            "site": {"name": "Studio"},
            "series": [{"name": "Studio"}, {"name": "Series A"}],
        }

        match = map_scene_to_match(scene)

        self.assertEqual(match.get("studio"), "Studio")
        self.assertEqual(match.get("Collection"), [{"tag": "Studio"}, {"tag": "Series A"}])

    def test_match_maps_performer_image_to_role_thumb(self):
        scene = {
            "id": "123",
            "title": "Scene",
            "performers": [{"id": "p1", "name": "Performer", "image": {"url": "https://img/p.jpg"}}],
        }

        match = map_scene_to_match(scene)

        self.assertEqual(
            match.get("Role"),
            [{"tag": "Performer", "id": "tv.plex.agents.custom.tpdb://person/p1", "key": "/library/metadata/person/p1", "url": "https://theporndb.net/performers/p1", "thumb": "https://img/p.jpg"}],
        )

    def test_map_scene_to_images_returns_unique_image_urls(self):
        scene = {
            "slug": "scene-slug",
            "images": {
                "poster": {"src": "https://img/poster.jpg"},
                "background": {"url": "https://img/bg.jpg"},
            },
        }

        images = map_scene_to_images(scene)
        image_types = {image["type"] for image in images}

        self.assertSetEqual(image_types, {"coverPoster", "background"})

    def test_map_scene_to_images_returns_empty_when_no_images(self):
        scene = {
            "slug": "scene-slug",
            "title": "Scene Without Artwork",
        }

        images = map_scene_to_images(scene)

        self.assertEqual(images, [])

    def test_legacy_scene_and_actor_image_fields_are_mapped(self):
        scene = {
            "slug": "scene-slug",
            "title": "Scene",
            "posters": {"large": "https://img/poster-large.jpg"},
            "background": {"full": "https://img/background-full.jpg"},
            "performers": [{"slug": "perf-slug", "name": "Performer", "face": "https://img/performer-face.jpg"}],
        }

        metadata = map_scene_to_metadata(scene)
        images = map_scene_to_images(scene)
        image_by_type = {image["type"]: image["url"] for image in images}

        self.assertEqual(metadata.get("thumb"), "https://img/poster-large.jpg")
        self.assertEqual(metadata.get("art"), "https://img/background-full.jpg")
        self.assertEqual(
            metadata.get("Role"),
            [{"tag": "Performer", "id": "tv.plex.agents.custom.tpdb://person/perf-slug", "key": "/library/metadata/person/perf-slug", "url": "https://theporndb.net/performers/perf-slug", "thumb": "https://img/performer-face.jpg"}],
        )
        self.assertEqual(image_by_type.get("coverPoster"), "https://img/poster-large.jpg")
        self.assertEqual(image_by_type.get("background"), "https://img/background-full.jpg")

    def test_role_identifier_prefers_performer_id_over_slug(self):
        scene = {
            "id": "123",
            "title": "Scene",
            "performers": [{"id": "performer-id", "slug": "performer-slug", "name": "Performer"}],
        }

        metadata = map_scene_to_metadata(scene)

        self.assertEqual(metadata.get("Role"), [{"tag": "Performer", "id": "tv.plex.agents.custom.tpdb://person/performer-id", "key": "/library/metadata/person/performer-id", "url": "https://theporndb.net/performers/performer-slug"}])

    # ------------------------------------------------------------------ #
    # Image selection: poster/background preference and VR screengrab fix  #
    # ------------------------------------------------------------------ #

    def test_poster_preferred_over_screengrab_in_images_list(self):
        """Poster-typed images should win even when a screengrab appears first."""
        scene = {
            "slug": "vr-scene",
            "images": [
                {"url": "https://img/screengrab.jpg", "type": "screengrab"},
                {"url": "https://img/poster.jpg", "type": "poster"},
            ],
        }

        metadata = map_scene_to_metadata(scene)
        match = map_scene_to_match(scene)

        self.assertEqual(metadata.get("thumb"), "https://img/poster.jpg")
        self.assertEqual(match.get("thumb"), "https://img/poster.jpg")

    def test_art_preferred_over_screengrab_in_images_list(self):
        """Background-typed images should win for the art slot."""
        scene = {
            "slug": "vr-scene",
            "images": [
                {"url": "https://img/screengrab.jpg", "type": "still"},
                {"url": "https://img/background.jpg", "type": "background"},
            ],
        }

        metadata = map_scene_to_metadata(scene)

        self.assertEqual(metadata.get("art"), "https://img/background.jpg")

    def test_portrait_dimensions_preferred_for_primary_poster(self):
        scene = {
            "slug": "mixed-orientation",
            "images": [
                {"url": "https://img/landscape.jpg", "width": 1600, "height": 900},
                {"url": "https://img/portrait.jpg", "width": 900, "height": 1350},
            ],
        }

        metadata = map_scene_to_metadata(scene)

        self.assertEqual(metadata.get("thumb"), "https://img/portrait.jpg")

    def test_landscape_dimensions_preferred_for_primary_art(self):
        scene = {
            "slug": "mixed-orientation",
            "images": [
                {"url": "https://img/portrait.jpg", "width": 900, "height": 1350},
                {"url": "https://img/landscape.jpg", "width": 1600, "height": 900},
            ],
        }

        metadata = map_scene_to_metadata(scene)

        self.assertEqual(metadata.get("art"), "https://img/landscape.jpg")

    def test_vr_scene_first_image_screengrab_last_is_poster(self):
        """Simulates a typical VR payload where the first list item is a screengrab."""
        scene = {
            "slug": "vr-scene-123",
            "title": "VR Scene",
            "images": [
                {"url": "https://cdn/vr-frame-001.jpg", "type": "screengrab"},
                {"url": "https://cdn/vr-frame-002.jpg", "type": "still"},
                {"url": "https://cdn/vr-poster.jpg", "type": "poster"},
                {"url": "https://cdn/vr-bg.jpg", "type": "fanart"},
            ],
        }

        metadata = map_scene_to_metadata(scene)
        match = map_scene_to_match(scene)
        images = map_scene_to_images(scene)
        image_by_type = {}
        for img in images:
            image_by_type.setdefault(img["type"], img["url"])

        # Best poster is the explicit poster, not the first screengrab
        self.assertEqual(metadata.get("thumb"), "https://cdn/vr-poster.jpg")
        self.assertEqual(match.get("thumb"), "https://cdn/vr-poster.jpg")
        # Best art is the fanart
        self.assertEqual(metadata.get("art"), "https://cdn/vr-bg.jpg")
        # map_scene_to_images primary slots
        self.assertEqual(image_by_type.get("coverPoster"), "https://cdn/vr-poster.jpg")
        self.assertEqual(image_by_type.get("background"), "https://cdn/vr-bg.jpg")

    def test_images_list_string_fallback_when_no_type_hints(self):
        """Plain string image lists without type hints are handled as generic candidates."""
        scene = {
            "slug": "scene-plain",
            "images": [
                "https://img/image1.jpg",
                "https://img/image2.jpg",
            ],
        }

        metadata = map_scene_to_metadata(scene)
        # Either image is acceptable as a generic candidate; the first should win
        self.assertEqual(metadata.get("thumb"), "https://img/image1.jpg")

    def test_top_level_poster_beats_images_list_screengrab(self):
        """A top-level poster field should win over a screengrab in scene.images."""
        scene = {
            "slug": "scene-x",
            "poster": "https://img/top-poster.jpg",
            "images": [
                {"url": "https://img/screengrab.jpg", "type": "screengrab"},
            ],
        }

        metadata = map_scene_to_metadata(scene)

        self.assertEqual(metadata.get("thumb"), "https://img/top-poster.jpg")

    def test_cover_url_beats_mislabelled_background_poster_field(self):
        """TPDB may expose a real cover as image and a background as poster."""
        scene = {
            "slug": "scene-cover",
            "image": "https://cdn.example/scene-cover-desktop.webp",
            "poster": "https://thumb.example/scene/background/bg-scene.jpg",
            "background": "https://cdn.example/scene/background/bg-scene.jpg",
        }

        metadata = map_scene_to_metadata(scene)
        images = map_scene_to_images(scene)

        self.assertEqual(metadata.get("thumb"), "https://cdn.example/scene-cover-desktop.webp")
        self.assertEqual(metadata.get("art"), "https://cdn.example/scene/background/bg-scene.jpg")
        self.assertEqual(images[0]["type"], "coverPoster")
        self.assertEqual(images[0]["url"], "https://cdn.example/scene-cover-desktop.webp")

    def test_encoded_background_url_does_not_outrank_cover(self):
        """TPDB thumbnail URLs encode the background path with percent escapes."""
        scene = {
            "slug": "scene-encoded",
            "image": "https://cdn.example/scene-cover.webp",
            "poster": "https://thumb.theporndb.net/x/scene%2Fbackground%2Fbg-scene.jpg",
            "background": "https://cdn.theporndb.net/scene/background/bg-scene.jpg",
        }

        metadata = map_scene_to_metadata(scene)

        self.assertEqual(metadata.get("thumb"), "https://cdn.example/scene-cover.webp")
        self.assertEqual(metadata.get("art"), "https://cdn.theporndb.net/scene/background/bg-scene.jpg")

    def test_map_scene_to_images_emits_multiple_poster_candidates(self):
        """When multiple poster-like images exist, map_scene_to_images emits them all."""
        scene = {
            "slug": "scene-multi",
            "images": [
                {"url": "https://img/poster1.jpg", "type": "poster"},
                {"url": "https://img/cover.jpg", "type": "cover"},
                {"url": "https://img/bg.jpg", "type": "background"},
            ],
        }

        images = map_scene_to_images(scene)
        poster_urls = [img["url"] for img in images if img["type"] == "coverPoster"]
        art_urls = [img["url"] for img in images if img["type"] == "background"]

        # Both poster-like candidates should be present
        self.assertIn("https://img/poster1.jpg", poster_urls)
        self.assertIn("https://img/cover.jpg", poster_urls)
        # Best art candidate
        self.assertIn("https://img/bg.jpg", art_urls)

    def test_map_scene_to_images_deduplicates_urls(self):
        """Duplicate URLs must appear only once regardless of type."""
        scene = {
            "slug": "scene-dup",
            "poster": "https://img/same.jpg",
            "background": "https://img/same.jpg",
        }

        images = map_scene_to_images(scene)
        urls = [img["url"] for img in images]

        self.assertEqual(urls.count("https://img/same.jpg"), 1)

    def test_screengrab_only_payload_still_returns_image(self):
        """When only screengrab images are present they are used as a last resort."""
        scene = {
            "slug": "scene-grab",
            "images": [
                {"url": "https://img/grab.jpg", "type": "screengrab"},
            ],
        }

        metadata = map_scene_to_metadata(scene)

        self.assertEqual(metadata.get("thumb"), "https://img/grab.jpg")

    def test_legacy_string_image_field_still_works(self):
        """Plain string values in top-level image fields remain supported."""
        scene = {
            "slug": "scene-legacy",
            "poster": "https://img/poster.jpg",
            "background": "https://img/bg.jpg",
        }

        metadata = map_scene_to_metadata(scene)

        self.assertEqual(metadata.get("thumb"), "https://img/poster.jpg")
        self.assertEqual(metadata.get("art"), "https://img/bg.jpg")

    def test_extract_scene_images_returns_list(self):
        """extract_scene_images() returns a list of {type, url} dicts."""
        scene = {
            "slug": "scene-fmt",
            "images": {
                "poster": {"src": "https://img/poster.jpg"},
                "background": {"url": "https://img/bg.jpg"},
            },
        }

        entries = extract_scene_images(scene)

        self.assertIsInstance(entries, list)
        types = {e["type"] for e in entries}
        self.assertIn("poster", types)
        self.assertIn("art", types)
        for entry in entries:
            self.assertIn("type", entry)
            self.assertIn("url", entry)


class MetadataHydrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_hydrates_performer_and_site_with_caching(self):
        service = MetadataService.__new__(MetadataService)
        service._performer_cache = OrderedDict()
        service._site_cache = OrderedDict()
        service.client = Mock()
        service.client.get_performer = AsyncMock(return_value={
            "id": "p1",
            "name": "Hydrated Performer",
            "image": "https://img/hydrated.jpg",
        })
        service.client.get_site = AsyncMock(return_value={"id": "s1", "name": "Hydrated Studio"})

        scene = {
            "id": "scene-1",
            "site": {"id": "s1"},
            "performers": [{"id": "p1", "name": "Inline Name"}],
        }

        hydrated = await service._hydrate_scene(dict(scene))
        hydrated_again = await service._hydrate_scene(dict(scene))

        self.assertEqual(hydrated["performers"][0]["name"], "Inline Name")
        self.assertEqual(hydrated["performers"][0]["image"], "https://img/hydrated.jpg")
        self.assertEqual(hydrated["site"]["name"], "Hydrated Studio")
        self.assertEqual(hydrated_again["site"]["name"], "Hydrated Studio")
        service.client.get_performer.assert_awaited_once_with("p1")
        service.client.get_site.assert_awaited_once_with("s1")

    async def test_hydrated_performer_name_used_when_inline_missing(self):
        service = MetadataService.__new__(MetadataService)
        service._performer_cache = OrderedDict()
        service._site_cache = OrderedDict()
        service.client = Mock()
        service.client.get_performer = AsyncMock(return_value={
            "id": "p2",
            "name": "Hydrated Name",
            "image": "https://img/hydrated-2.jpg",
        })
        service.client.get_site = AsyncMock(return_value=None)

        scene = {
            "id": "scene-2",
            "performers": [{"id": "p2"}],
        }

        hydrated = await service._hydrate_scene(scene)

        self.assertEqual(hydrated["performers"][0]["name"], "Hydrated Name")


if __name__ == "__main__":
    unittest.main()
