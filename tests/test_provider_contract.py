import json
import unittest
from unittest.mock import AsyncMock, Mock, patch

from fastapi import HTTPException
from starlette.requests import Request

from provider.mappers.tpdb_to_plex import extract_scene_images
from provider.models import plex_page
from provider.routes.manifest import get_manifest
from provider.routes.matches import match_media
from provider.services.match_service import MatchService


def request(body=None, query="", headers=()):
    async def receive():
        return {"type": "http.request", "body": json.dumps(body).encode()}
    return Request({"type": "http", "method": "POST", "path": "/",
                    "headers": list(headers), "query_string": query.encode()}, receive)


class ProviderContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_automatic_and_manual_matches(self):
        service = Mock(search=AsyncMock(return_value=[{"title": "Best"}, {"title": "Other"}]))
        with patch("provider.routes.matches.get_match_service", return_value=service):
            for manual, count in [(0, 1), (1, 2)]:
                response = await match_media(request({"type": 1, "title": "Scene", "manual": manual}))
                self.assertEqual(json.loads(response.body)["MediaContainer"]["size"], count)

    async def test_invalid_match_is_bad_request(self):
        for body in [{}, {"type": 1, "title": "Scene", "manual": 2}, []]:
            with self.assertRaises(HTTPException) as caught:
                await match_media(request(body))
            self.assertEqual(caught.exception.status_code, 400)

    def test_query_paging_and_header_precedence(self):
        query = "X-Plex-Container-Start=1&X-Plex-Container-Size=1"
        self.assertEqual(plex_page(request(query=query), [1, 2, 3]), (1, [2]))
        self.assertEqual(plex_page(request(query=query, headers=[(b"x-plex-container-start", b"0")]), [1, 2]), (0, [1]))
        with self.assertRaises(HTTPException):
            plex_page(request(query="X-Plex-Container-Size=-1"), [])

    async def test_known_guid_avoids_title_search(self):
        service = MatchService.__new__(MatchService)
        service.client = Mock(get_scene=AsyncMock(return_value={"id": "abc", "slug": "abc", "title": "Scene"}))
        for guid in ["tpdb://abc", "tv.plex.agents.custom.tpdb://movie/abc"]:
            results = await service.search("Scene", guid=guid)
            self.assertEqual(len(results), 1)
            service.client.get_scene.assert_awaited_with("abc")

    def test_documented_artwork_fields_and_deduplication(self):
        images = extract_scene_images({"poster_image": "https://cdn/p.jpg",
                                       "back_image": "https://cdn/b.jpg",
                                       "background_back": {"full": "https://cdn/b.jpg"}})
        self.assertTrue(any(i["url"] == "https://cdn/p.jpg" and i["type"] == "poster" for i in images))
        self.assertTrue(any(i["url"] == "https://cdn/b.jpg" and i["type"] == "art" for i in images))

    async def test_manifest_advertises_documented_movie_type(self):
        response = await get_manifest()
        self.assertEqual([i["type"] for i in json.loads(response.body)["MediaProvider"]["Types"]], [1])
