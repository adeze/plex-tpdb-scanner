import json
import unittest
from unittest.mock import AsyncMock, Mock, patch

from fastapi import HTTPException

from provider.routes import metadata as metadata_routes


class MetadataRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_image_proxies_selected_scene_image(self):
        service = Mock()
        service.get_scene = AsyncMock(return_value={
            "slug": "scene-slug",
            "image": "https://cdn.example/cover.jpg",
        })
        upstream = Mock(status_code=200, content=b"jpeg-bytes")
        upstream.headers = {"content-type": "image/jpeg"}
        client = Mock()
        client.get = AsyncMock(return_value=upstream)

        with patch("provider.routes.metadata.get_metadata_service", return_value=service), patch(
            "provider.routes.metadata.get_image_client", return_value=client
        ):
            response = await metadata_routes.get_image("scene-slug", "poster", 0)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.body, b"jpeg-bytes")
        self.assertEqual(response.media_type, "image/jpeg")
        client.get.assert_awaited_once_with("https://cdn.example/cover.jpg")

    async def test_get_metadata_images_returns_entries(self):
        service = Mock()
        service.get_images = AsyncMock(return_value=[
            {
                "type": "coverPoster",
                "url": "https://img/poster.jpg",
                "key": "/library/metadata/scene-slug/images/poster",
                "ratingKey": "scene-slug",
                "provider": "tv.plex.agents.custom.tpdb",
            }
        ])

        with patch("provider.routes.metadata.get_metadata_service", return_value=service):
            response = await metadata_routes.get_metadata_images("scene-slug", Mock(headers={}))

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["MediaContainer"]["size"], 1)
        self.assertEqual(payload["MediaContainer"]["Image"][0]["type"], "coverPoster")
        service.get_images.assert_awaited_once_with("scene-slug")

    async def test_get_metadata_images_returns_404_for_missing_scene(self):
        service = Mock()
        service.get_images = AsyncMock(return_value=None)

        with patch("provider.routes.metadata.get_metadata_service", return_value=service):
            with self.assertRaises(HTTPException) as context:
                await metadata_routes.get_metadata_images("missing-scene", Mock(headers={}))

        self.assertEqual(context.exception.status_code, 404)
        service.get_images.assert_awaited_once_with("missing-scene")

    async def test_get_metadata_images_returns_empty_list_for_scene_without_images(self):
        service = Mock()
        service.get_images = AsyncMock(return_value=[])

        with patch("provider.routes.metadata.get_metadata_service", return_value=service):
            response = await metadata_routes.get_metadata_images("scene-slug", Mock(headers={}))

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["MediaContainer"]["size"], 0)
        self.assertEqual(payload["MediaContainer"]["totalSize"], 0)
        self.assertEqual(payload["MediaContainer"]["Image"], [])
        service.get_images.assert_awaited_once_with("scene-slug")

    async def test_get_metadata_response_unchanged(self):
        service = Mock()
        service.get_metadata = AsyncMock(return_value={
            "type": "movie",
            "guid": "tv.plex.agents.custom.tpdb://movie/scene-slug",
            "key": "/library/metadata/scene-slug",
            "ratingKey": "scene-slug",
            "title": "Scene",
        })

        with patch("provider.routes.metadata.get_metadata_service", return_value=service):
            response = await metadata_routes.get_metadata("scene-slug")

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["MediaContainer"]["size"], 1)
        self.assertEqual(payload["MediaContainer"]["Metadata"][0]["ratingKey"], "scene-slug")
        service.get_metadata.assert_awaited_once_with("scene-slug")

    async def test_get_person_metadata_returns_plex_person(self):
        service = Mock()
        service.get_performer_metadata = AsyncMock(return_value={
            "type": "person",
            "guid": "tv.plex.agents.custom.tpdb://person/p1",
            "key": "/library/metadata/person/p1",
            "ratingKey": "p1",
            "title": "Performer",
            "url": "https://theporndb.net/performers/performer",
        })

        with patch("provider.routes.metadata.get_metadata_service", return_value=service):
            response = await metadata_routes.get_person_metadata("p1")

        payload = json.loads(response.body)
        person = payload["MediaContainer"]["Metadata"][0]
        self.assertEqual(response.status_code, 200)
        self.assertEqual(person["type"], "person")
        self.assertEqual(person["url"], "https://theporndb.net/performers/performer")
        service.get_performer_metadata.assert_awaited_once_with("p1")


if __name__ == "__main__":
    unittest.main()
