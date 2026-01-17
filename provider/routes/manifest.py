"""Provider manifest endpoint."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()

PROVIDER_IDENTIFIER = "tv.plex.agents.custom.tpdb"
PROVIDER_TITLE = "ThePornDB"


@router.get("/")
async def get_manifest():
    """Return the provider manifest for Plex discovery."""
    manifest = {
        "MediaProvider": {
            "identifier": PROVIDER_IDENTIFIER,
            "title": PROVIDER_TITLE,
            "Types": [
                {
                    "type": 1,  # Movie type
                    "Scheme": [{"scheme": PROVIDER_IDENTIFIER}],
                },
                {
                    "type": 4,  # Other Videos type
                    "Scheme": [{"scheme": PROVIDER_IDENTIFIER}],
                },
            ],
            "Feature": [
                {"type": "match", "key": "/library/metadata/matches"},
                {"type": "metadata", "key": "/library/metadata"},
            ],
        }
    }
    return JSONResponse(content=manifest)
