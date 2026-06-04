import json
import unittest
from unittest.mock import Mock, patch

from fastapi import HTTPException

from provider.routes import metadata as metadata_routes


class MetadataRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_metadata_images_returns_entries(self):
        service = Mock()
        service.get_images.return_value = [
            {
                "type": "poster",
                "url": "https://img/poster.jpg",
                "key": "/library/metadata/scene-slug/images/poster",
                "ratingKey": "scene-slug",
                "provider": "tv.plex.agents.custom.tpdb",
            }
        ]

        with patch("provider.routes.metadata.get_metadata_service", return_value=service):
            response = await metadata_routes.get_metadata_images("scene-slug")

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["MediaContainer"]["size"], 1)
        self.assertEqual(payload["MediaContainer"]["Metadata"][0]["type"], "poster")
        service.get_images.assert_called_once_with("scene-slug")

    async def test_get_metadata_images_returns_404_for_missing_scene(self):
        service = Mock()
        service.get_images.return_value = None

        with patch("provider.routes.metadata.get_metadata_service", return_value=service):
            with self.assertRaises(HTTPException) as context:
                await metadata_routes.get_metadata_images("missing-scene")

        self.assertEqual(context.exception.status_code, 404)
        service.get_images.assert_called_once_with("missing-scene")

    async def test_get_metadata_images_returns_empty_list_for_scene_without_images(self):
        service = Mock()
        service.get_images.return_value = []

        with patch("provider.routes.metadata.get_metadata_service", return_value=service):
            response = await metadata_routes.get_metadata_images("scene-slug")

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["MediaContainer"]["size"], 0)
        self.assertEqual(payload["MediaContainer"]["totalSize"], 0)
        self.assertEqual(payload["MediaContainer"]["Metadata"], [])
        service.get_images.assert_called_once_with("scene-slug")

    async def test_get_metadata_response_unchanged(self):
        service = Mock()
        service.get_metadata.return_value = {
            "type": "movie",
            "guid": "tv.plex.agents.custom.tpdb://movie/scene-slug",
            "key": "/library/metadata/scene-slug",
            "ratingKey": "scene-slug",
            "title": "Scene",
        }

        with patch("provider.routes.metadata.get_metadata_service", return_value=service):
            response = await metadata_routes.get_metadata("scene-slug")

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["MediaContainer"]["size"], 1)
        self.assertEqual(payload["MediaContainer"]["Metadata"][0]["ratingKey"], "scene-slug")
        service.get_metadata.assert_called_once_with("scene-slug")


if __name__ == "__main__":
    unittest.main()
