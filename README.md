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

## Quick Start

### 1. Get your API key

Get your API key from: https://theporndb.net (create account > API settings)

### 2. Deploy the Provider

**Using Docker Compose (recommended):**

```bash
# Clone the repository
git clone https://github.com/mystrock/plex-tpdb-scanner.git
cd plex-tpdb-scanner

# Set your API key
export TPDB_API_KEY=your_api_key_here

# Start the provider
docker-compose up -d
```

**Using the pre-built image:**

```bash
docker run -d \
  --name tpdb-provider \
  -p 32500:32500 \
  -e TPDB_API_KEY=your_api_key_here \
  ghcr.io/mystrock/plex-tpdb-scanner:latest
```

**Running directly with Python:**

```bash
pip install -r requirements.txt
export TPDB_API_KEY=your_api_key_here
python -m uvicorn provider.main:app --host 0.0.0.0 --port 32500
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
| `TPDB_LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `TPDB_PUBLIC_URL` | (optional) | URL Plex uses to reach on-demand provider image endpoints |

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

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Provider manifest |
| `/library/metadata/matches` | POST | Search for matching scenes |
| `/library/metadata/{id}` | GET | Get full metadata for a scene |
| `/library/metadata/{id}/images` | GET | Get image metadata entries for a scene |

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
# Install dependencies
pip install -r requirements.txt

# Run in development mode with auto-reload
uvicorn provider.main:app --reload --port 32500

# Run with debug logging
TPDB_LOG_LEVEL=DEBUG uvicorn provider.main:app --port 32500
```

## License

MIT License
