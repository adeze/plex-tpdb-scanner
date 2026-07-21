# TPDB Plex Metadata Provider

A Plex Metadata Provider for ThePornDB, compatible with Plex Media Server 1.43+.

This solution uses the new Plex Metadata Provider API to fetch metadata directly from ThePornDB when Plex scans your library.

## Architecture

```
Plex Media Server  <-->  TPDB Provider (FastAPI)  <-->  ThePornDB API
     :32400                   :32500                    api.theporndb.net
```

## Requirements

- Plex Media Server 1.43 or later
- Docker (recommended) or Python 3.11+
- ThePornDB API key

## Package management

This project uses [uv](https://docs.astral.sh/uv/) as the canonical Python project and dependency manager.

- `pyproject.toml` declares project metadata and direct dependencies.
- `uv.lock` pins the complete resolved dependency graph.
- `requirements.txt` and `requirements-dev.txt` are generated compatibility exports.
- Docker and CI install from `uv.lock`; do not edit generated requirements files by hand.

Install or update dependencies with:

```bash
uv sync --dev
uv add package-name
uv add --dev development-package-name
uv lock
```

Run commands in the locked environment with `uv run`:

```bash
uv run python -m unittest discover -s tests -p 'test_*.py'
```

## Quick Start

### 1. Get your API key

Get your API key from: https://theporndb.net (create account > API settings)

### 2. Deploy the Provider

**Using Docker Compose (recommended):**

```bash
# Clone the repository
git clone https://github.com/adeze/plex-tpdb-scanner.git
cd plex-tpdb-scanner

# Set your API key
export TPDB_API_KEY=your_api_key_here

# Start the provider
docker compose up -d --build
```

**Using the pre-built image:**

```bash
docker run -d \
  --name tpdb-provider \
  -p 32500:32500 \
  -e TPDB_API_KEY=your_api_key_here \
  ghcr.io/adeze/plex-tpdb-scanner:latest
```

**Running directly with Python:**

```bash
uv sync
export TPDB_API_KEY=your_api_key_here
uv run uvicorn provider.main:app --host 0.0.0.0 --port 32500
```

### 3. Configure Plex

1. Open Plex Web App
2. Go to **Settings > Agents** (under Manage)
3. Click **Add Custom Provider**
4. Enter the provider URL: `http://<your-server-ip>:32500`
5. Click **Add Provider**

### 4. Create/Update Your Library

1. Go to **Settings > Libraries**
2. Create a new library or edit an existing one
3. In **Advanced** settings:
   - Enable **ThePornDB** as a metadata source
   - Drag it to the top of the list if you want it as the primary source
4. Scan your library

## Configuration

The provider uses environment variables for configuration:

| Variable | Default | Description |
|----------|---------|-------------|
| `TPDB_API_KEY` | (required) | Your ThePornDB API key |
| `TPDB_PORT` | `32500` | Port the provider listens on | 
| `TPDB_LOG_LEVEL` | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

## How It Works

When Plex scans your library, it sends the filename/title to the provider. The provider:

1. Searches ThePornDB for matching scenes
2. Returns potential matches with scores
3. When Plex selects a match, fetches full metadata including:
   - Title, release date, summary
- Poster and fanart images
   - Studio name
   - Performers with photos
- Tags/genres

Artwork is returned as direct TPDB HTTPS URLs using Plex's modern `Image` asset contract. Plex remains responsible for downloading and caching artwork; the provider does not write to Plex's database or `Media` cache.

The provider uses `httpx2.AsyncClient` for pooled asynchronous TPDB and image requests, `rapidfuzz` for candidate ranking, and Pydantic models for Plex request and response envelopes.

## Matching behavior

Matching normalizes filenames before searching by removing technical release tokens such as resolution, codecs, fisheye markers, and VR projection labels. Returned candidates are then ranked using:

- Fuzzy title similarity
- Studio/site similarity
- Performer overlap
- Release-year proximity

Plex receives the ranked candidates and their scores, so ambiguous results can still be confirmed through **Fix Match**.

## Rate limiting

TPDB requests are paced through one process-wide limiter at a conservative two requests per second. The client also honors `Retry-After` on `429` responses, observes rate-limit headers when present, and retries rate-limited requests with bounded backoff. This protects the API during concurrent Plex refreshes while allowing the provider's HTTP handlers to remain asynchronous.

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Provider manifest |
| `/library/metadata/matches` | POST | Search for matching scenes |
| `/library/metadata/{id}` | GET | Get full metadata for a scene |
| `/library/metadata/{id}/images` | GET | Get image metadata entries for a scene |
| `/library/metadata/{id}/extras` | GET | Return an empty extras collection |

## Verification

Test the provider is running:

```bash
# Check manifest
curl http://localhost:32500/

# Test search
curl -X POST http://localhost:32500/library/metadata/matches \
  -H "Content-Type: application/json" \
  -d '{"type":1,"title":"scene title here"}'
```

## Troubleshooting

### Provider not appearing in Plex

- Verify the provider is running: `curl http://localhost:32500/`
- Check the provider URL is accessible from your Plex server
- Restart Plex Media Server after adding the provider

### No matches found

- Verify your API key is correct
- Check provider logs for errors: `docker logs tpdb-provider`
- Try searching for the scene manually on theporndb.net

### Metadata not loading

- Check that the provider is selected in your library's advanced settings
- Try "Refresh Metadata" on a specific item
- Check provider logs for API errors

## Development

```bash
# Install dependencies and create the locked environment
uv sync --dev

# Run in development mode with auto-reload
uv run uvicorn provider.main:app --reload --port 32500

# Run with debug logging
TPDB_LOG_LEVEL=DEBUG uv run uvicorn provider.main:app --port 32500

# Run tests
uv run python -m unittest discover -s tests -p 'test_*.py'
```

## Releases

Releases use semantic version tags such as `v0.2.0`. Releases are currently published manually: run the test suite, create a Git tag and GitHub Release, then build and push matching Docker tags to GHCR. Deploy a versioned image tag for reproducibility rather than relying on `latest`.

```bash
docker build -t ghcr.io/adeze/plex-tpdb-scanner:0.2.0 .
docker tag ghcr.io/adeze/plex-tpdb-scanner:0.2.0 ghcr.io/adeze/plex-tpdb-scanner:latest
docker push ghcr.io/adeze/plex-tpdb-scanner:0.2.0
docker push ghcr.io/adeze/plex-tpdb-scanner:latest
```

## License

MIT License
