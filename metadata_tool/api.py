#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ThePornDB API Client
"""

import time
import logging
import requests
import asyncio
import httpx2
from urllib.parse import quote, urlencode

BASE_URL = 'https://api.theporndb.net'
RATE_LIMIT_DELAY = 0.5  # 120 requests/min = 0.5s between requests
logger = logging.getLogger(__name__)


class AsyncRateLimiter:
    """Process-wide pacing for all async TPDB clients."""

    def __init__(self, minimum_interval: float = RATE_LIMIT_DELAY):
        self.minimum_interval = minimum_interval
        self._lock = asyncio.Lock()
        self._last_request_time = 0.0

    async def wait(self):
        async with self._lock:
            elapsed = time.monotonic() - self._last_request_time
            if elapsed < self.minimum_interval:
                await asyncio.sleep(self.minimum_interval - elapsed)
            self._last_request_time = time.monotonic()


_ASYNC_RATE_LIMITER = AsyncRateLimiter()


class TPDBApiError(Exception):
    """API Error with status code and message."""
    def __init__(self, status_code, message):
        self.status_code = status_code
        self.message = message
        super().__init__(f'API Error {status_code}: {message}')


class TPDBClient:
    """Client for ThePornDB API."""

    def __init__(self, api_key):
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {api_key}',
            'Accept': 'application/json',
            'User-Agent': 'TPDB-Plex-Scanner/1.0'
        })
        self.last_request_time = 0

    def _rate_limit(self):
        """Enforce rate limiting."""
        elapsed = time.time() - self.last_request_time
        if elapsed < RATE_LIMIT_DELAY:
            time.sleep(RATE_LIMIT_DELAY - elapsed)
        self.last_request_time = time.time()

    def _request(self, method, endpoint, params=None):
        """Make an API request."""
        self._rate_limit()

        url = f'{BASE_URL}{endpoint}'

        try:
            if method == 'GET':
                response = self.session.get(url, params=params, timeout=30)
            else:
                response = self.session.post(url, json=params, timeout=30)

            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                return None
            elif response.status_code == 429:
                # Rate limited - wait and retry
                time.sleep(5)
                return self._request(method, endpoint, params)
            else:
                error_msg = response.json().get('message', response.text)
                raise TPDBApiError(response.status_code, error_msg)

        except requests.exceptions.RequestException as e:
            raise TPDBApiError(0, str(e))

    def search_scenes(self, query, year=None, hash=None):
        """
        Search for scenes.

        Args:
            query: Search query (studio + title)
            year: Optional release year
            hash: Optional file hash

        Returns:
            List of scene results or empty list
        """
        params = {'parse': query}
        if year:
            params['year'] = year
        if hash:
            params['hash'] = hash

        result = self._request('GET', '/scenes', params)
        if result and 'data' in result:
            return result['data']
        return []

    def get_scene(self, scene_id):
        """
        Get scene details by ID.

        Args:
            scene_id: Scene ID or slug

        Returns:
            Scene data dict or None
        """
        result = self._request('GET', f'/scenes/{scene_id}')
        if result and 'data' in result:
            return result['data']
        return None

    def get_performer(self, performer_id):
        """Get performer details using the synchronous client."""
        result = self._request('GET', f'/performers/{performer_id}')
        if result and 'data' in result:
            return result['data']
        return None

    def get_site(self, site_id):
        """Get site details using the synchronous client."""
        result = self._request('GET', f'/sites/{site_id}')
        if result and 'data' in result:
            return result['data']
        return None


class AsyncTPDBClient:
    """Async ThePornDB client with pooled connections and bounded retries."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.client = httpx2.AsyncClient(
            base_url=BASE_URL,
            headers={
                'Authorization': f'Bearer {api_key}',
                'Accept': 'application/json',
                'User-Agent': 'TPDB-Plex-Scanner/1.0',
            },
            timeout=httpx2.Timeout(30.0),
            http2=True,
        )
    async def _request(self, method: str, endpoint: str, params=None):
        """Make an async API request with bounded rate-limit retries."""
        for attempt in range(4):
            await _ASYNC_RATE_LIMITER.wait()
            started = time.perf_counter()
            try:
                response = await self.client.request(method, endpoint, params=params)
            except httpx2.HTTPError as exc:
                logger.error(
                    "event=tpdb_request method=%s endpoint=%s status=transport_error attempt=%d duration_ms=%.1f error=%s",
                    method,
                    endpoint,
                    attempt + 1,
                    (time.perf_counter() - started) * 1000,
                    type(exc).__name__,
                )
                raise TPDBApiError(0, str(exc)) from exc

            duration_ms = (time.perf_counter() - started) * 1000
            logger.info(
                "event=tpdb_request method=%s endpoint=%s status=%d attempt=%d duration_ms=%.1f",
                method,
                endpoint,
                response.status_code,
                attempt + 1,
                duration_ms,
            )

            if response.status_code == 200:
                return response.json()
            if response.status_code == 404:
                return None
            if response.status_code == 429 and attempt < 3:
                retry_after = response.headers.get("Retry-After")
                try:
                    delay = max(float(retry_after), 1.0) if retry_after else 5 * (attempt + 1)
                except ValueError:
                    delay = 5 * (attempt + 1)
                logger.warning(
                    "event=tpdb_rate_limit endpoint=%s retry_after_s=%.1f attempt=%d",
                    endpoint,
                    delay,
                    attempt + 1,
                )
                await asyncio.sleep(delay)
                continue

            remaining = response.headers.get("X-RateLimit-Remaining")
            if remaining is not None:
                try:
                    if int(remaining) <= 1:
                        reset = float(response.headers.get("X-RateLimit-Reset", "0"))
                        if reset > time.time():
                            await asyncio.sleep(min(reset - time.time(), 60.0))
                except ValueError:
                    pass

            try:
                error_msg = response.json().get('message', response.text)
            except ValueError:
                error_msg = response.text
            raise TPDBApiError(response.status_code, error_msg)

        return None

    async def search_scenes(self, query: str, year=None, hash=None):
        params = {'parse': query}
        if year:
            params['year'] = year
        if hash:
            params['hash'] = hash
        result = await self._request('GET', '/scenes', params)
        return result.get('data', []) if result and 'data' in result else []

    async def get_scene(self, scene_id: str):
        result = await self._request('GET', f'/scenes/{scene_id}')
        return result.get('data') if result and 'data' in result else None

    async def get_performer(self, performer_id: str):
        result = await self._request('GET', f'/performers/{performer_id}')
        return result.get('data') if result and 'data' in result else None

    async def get_site(self, site_id: str):
        result = await self._request('GET', f'/sites/{site_id}')
        return result.get('data') if result and 'data' in result else None

    async def close(self):
        await self.client.aclose()

def download_image(url, output_path, session=None):
    """
    Download an image from URL.

    Args:
        url: Image URL
        output_path: Path to save image
        session: Optional requests session

    Returns:
        True if successful, False otherwise
    """
    if not url:
        return False

    try:
        sess = session or requests.Session()
        response = sess.get(url, timeout=60, stream=True)

        if response.status_code == 200:
            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            return True

    except Exception as e:
        print(f'Error downloading {url}: {e}')

    return False
