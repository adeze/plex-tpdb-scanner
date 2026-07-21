# AGENTS.md

## Repository overview

This repository is a FastAPI-based Plex Metadata Provider for ThePornDB. Plex
calls the provider on port `32500`; the provider queries the ThePornDB API and
maps scene data into Plex metadata responses.

## Project layout

- `provider/main.py`: FastAPI application and request logging.
- `provider/config.py`: Environment-backed settings.
- `provider/routes/`: Plex manifest, match, metadata, and image endpoints.
- `provider/services/`: ThePornDB lookup, hydration, caching, and orchestration.
- `provider/mappers/tpdb_to_plex.py`: TPDB-to-Plex field and image mapping.
- `metadata_tool/api.py`: ThePornDB HTTP client, authentication, rate limiting,
  retries, and related resource lookups.
- `tests/`: Unit tests using mocked API/service calls.
- `Dockerfile`, `docker-compose.yml`, and `docker-compose.portainer.yml`: Local
  build and container deployment options.

## Configuration

Required environment variable:

- `TPDB_API_KEY`: ThePornDB API key.

Optional environment variables:

- `TPDB_PORT`: Provider port, defaults to `32500`.
- `TPDB_LOG_LEVEL`: Logging level, defaults to `INFO`.

Do not commit `.env` files, API keys, or other credentials.

## Development commands

Install dependencies:

```bash
pip install -r requirements.txt
```

Run locally:

```bash
TPDB_API_KEY=your_key uvicorn provider.main:app --reload --port 32500
```

Run with Docker Compose:

```bash
TPDB_API_KEY=your_key docker-compose up -d
```

## API contract

- `GET /`: Plex provider manifest.
- `POST /library/metadata/matches`: Search TPDB and return Plex match entries.
- `GET /library/metadata/{rating_key}`: Return full scene metadata.
- `GET /library/metadata/{rating_key}/images`: Return Plex image entries.

The provider supports Plex media types `1` (movie) and `4` (other video). Scene
IDs/slugs are used as Plex rating keys. Image mapping should preserve poster
and background/art fallbacks and avoid duplicate image URLs.

## Change guidance

- Keep TPDB API access in `metadata_tool/api.py` and provider orchestration in
  `provider/services/`.
- Keep Plex response-shape conversions in `provider/mappers/`.
- Preserve existing fallback handling for nested and legacy TPDB image fields.
- Use the existing in-memory caches for repeated performer and site lookups.
- Prefer focused unit tests with mocked TPDB responses for mapping and route
  changes; do not require network access in tests.
- Do not log API keys or other sensitive request data.
- Image proxying is on-demand for matched TPDB scenes; it does not scan or
  download images for the whole library.

## Reference documentation

- Plex Media Server API: https://developer.plex.tv/pms/
- Plex Metadata Agents: https://developer.plex.tv/pms/#tag/Metadata-Agents
- Plex Provider API: https://developer.plex.tv/pms/#tag/Provider
- ThePornDB API documentation: https://api.theporndb.net/docs
- ThePornDB tools: https://theporndb.net/tools
