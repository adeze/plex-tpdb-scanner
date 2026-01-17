#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ThePornDB API Client
"""

import time
import requests
from urllib.parse import quote, urlencode

BASE_URL = 'https://api.theporndb.net'
RATE_LIMIT_DELAY = 0.5  # 120 requests/min = 0.5s between requests


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

    def search_scene_by_title(self, studio, title, date=None):
        """
        Search for a scene by studio, title, and optional date.

        Args:
            studio: Studio/site name
            title: Scene title
            date: Optional date in YYYY-MM-DD format

        Returns:
            Best matching scene or None
        """
        # Build search query
        query = f'{studio} {title}'
        year = date.split('-')[0] if date else None

        results = self.search_scenes(query, year=year)

        if not results:
            # Try with just the title
            results = self.search_scenes(title, year=year)

        if results:
            # If we have a date, try to find exact match
            if date:
                for scene in results:
                    scene_date = scene.get('date', '')
                    if scene_date == date:
                        return scene

            # Return first result as best match
            return results[0]

        return None

    def get_performer(self, performer_id):
        """
        Get performer details.

        Args:
            performer_id: Performer ID or slug

        Returns:
            Performer data dict or None
        """
        result = self._request('GET', f'/performers/{performer_id}')
        if result and 'data' in result:
            return result['data']
        return None

    def get_site(self, site_id):
        """
        Get site/studio details.

        Args:
            site_id: Site ID or slug

        Returns:
            Site data dict or None
        """
        result = self._request('GET', f'/sites/{site_id}')
        if result and 'data' in result:
            return result['data']
        return None


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
