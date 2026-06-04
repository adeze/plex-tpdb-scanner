import unittest
from collections import OrderedDict
from unittest.mock import Mock

from provider.mappers.tpdb_to_plex import map_scene_to_match, map_scene_to_metadata
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
            "performers": [{"name": "Performer", "thumb": "https://img/p.jpg"}],
            "directors": [{"name": "Director One"}, {"name": "Director Two"}],
            "series": [{"name": "Series A"}],
            "franchise": "Franchise B",
        }

        metadata = map_scene_to_metadata(scene)

        self.assertEqual(metadata.get("thumb"), "https://img/poster.jpg")
        self.assertEqual(metadata.get("art"), "https://img/art.jpg")
        self.assertEqual(metadata.get("Director"), [{"tag": "Director One"}, {"tag": "Director Two"}])
        self.assertEqual(
            metadata.get("Collection"),
            [{"tag": "Series A"}, {"tag": "Franchise B"}],
        )
        self.assertEqual(metadata.get("Role"), [{"tag": "Performer", "thumb": "https://img/p.jpg"}])

    def test_match_supports_nested_images(self):
        scene = {
            "id": "123",
            "title": "Scene",
            "images": {
                "poster": {"src": "https://img/poster.jpg"},
                "background": {"url": "https://img/bg.jpg"},
            },
        }

        match = map_scene_to_match(scene)

        self.assertEqual(match.get("thumb"), "https://img/poster.jpg")
        self.assertEqual(match.get("art"), "https://img/bg.jpg")


class MetadataHydrationTests(unittest.TestCase):
    def test_hydrates_performer_and_site_with_caching(self):
        service = MetadataService.__new__(MetadataService)
        service._performer_cache = OrderedDict()
        service._site_cache = OrderedDict()
        service.client = Mock()
        service.client.get_performer.return_value = {
            "id": "p1",
            "name": "Hydrated Performer",
            "image": "https://img/hydrated.jpg",
        }
        service.client.get_site.return_value = {"id": "s1", "name": "Hydrated Studio"}

        scene = {
            "id": "scene-1",
            "site": {"id": "s1"},
            "performers": [{"id": "p1", "name": "Inline Name"}],
        }

        hydrated = service._hydrate_scene(dict(scene))
        hydrated_again = service._hydrate_scene(dict(scene))

        self.assertEqual(hydrated["performers"][0]["name"], "Inline Name")
        self.assertEqual(hydrated["performers"][0]["image"], "https://img/hydrated.jpg")
        self.assertEqual(hydrated["site"]["name"], "Hydrated Studio")
        self.assertEqual(hydrated_again["site"]["name"], "Hydrated Studio")
        service.client.get_performer.assert_called_once_with("p1")
        service.client.get_site.assert_called_once_with("s1")

    def test_hydrated_performer_name_used_when_inline_missing(self):
        service = MetadataService.__new__(MetadataService)
        service._performer_cache = OrderedDict()
        service._site_cache = OrderedDict()
        service.client = Mock()
        service.client.get_performer.return_value = {
            "id": "p2",
            "name": "Hydrated Name",
            "image": "https://img/hydrated-2.jpg",
        }
        service.client.get_site.return_value = None

        scene = {
            "id": "scene-2",
            "performers": [{"id": "p2"}],
        }

        hydrated = service._hydrate_scene(scene)

        self.assertEqual(hydrated["performers"][0]["name"], "Hydrated Name")


if __name__ == "__main__":
    unittest.main()
