"""
Google Drive client — lists Meet recordings and downloads audio.

Rules enforced here:
- Audio bytes are returned to the caller in memory and never written to disk.
- Callers (Celery tasks) MUST del the audio bytes immediately after transcription.
- Token refresh is a separate explicit call — never silently retried.

Async functions are used for FastAPI route handlers.
Sync functions are used inside Celery tasks.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from pydantic import BaseModel

from src.config import settings

logger = logging.getLogger(__name__)

_DRIVE_FILES_URL = "https://www.googleapis.com/drive/v3/files"
_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"  # noqa: S105

# Google Meet recordings land in Drive as video/mp4 files.
# We also check video/webm as some older Meet versions used it.
_RECORDING_MIME_TYPES = ("video/mp4", "video/webm", "video/quicktime")


class DriveRecording(BaseModel):
    file_id: str
    name: str
    created_time: datetime
    size_bytes: int | None = None
    mime_type: str


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------


async def refresh_access_token(refresh_token: str) -> str:
    """Exchange a Google refresh token for a fresh access token (async)."""
    payload = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            _TOKEN_ENDPOINT,
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    response.raise_for_status()
    data = response.json()
    token: str | None = data.get("access_token")
    if not token:
        raise ValueError("Token refresh response missing access_token")
    return token


def refresh_access_token_sync(refresh_token: str) -> str:
    """Exchange a Google refresh token for a fresh access token (sync, for Celery tasks)."""
    payload = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }
    with httpx.Client(timeout=10.0) as client:
        response = client.post(
            _TOKEN_ENDPOINT,
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    response.raise_for_status()
    data = response.json()
    token: str | None = data.get("access_token")
    if not token:
        raise ValueError("Token refresh response missing access_token")
    return token


# ---------------------------------------------------------------------------
# Drive listing (async — used by FastAPI routes)
# ---------------------------------------------------------------------------


async def _get_meet_folder_ids(
    client: httpx.AsyncClient,
    access_token: str,
) -> list[str]:
    """Return the Drive folder IDs for all folders named 'Meet Recordings'.

    Google Meet automatically saves recordings to a folder with this name.
    Returns an empty list if no such folder exists (user has no recordings yet).
    """
    params = {
        "q": "mimeType='application/vnd.google-apps.folder' and name='Meet Recordings' and trashed=false",
        "fields": "files(id)",
        "pageSize": "10",
    }
    response = await client.get(
        _DRIVE_FILES_URL,
        params=params,
        headers={"Authorization": f"Bearer {access_token}"},
    )
    if response.status_code == 401:
        raise PermissionError("Google access token is invalid or expired")
    response.raise_for_status()
    return [f["id"] for f in response.json().get("files", [])]


async def list_meet_recordings(
    access_token: str,
    lookback_days: int = 365,
) -> list[DriveRecording]:
    """List Google Meet recording files from Drive created in the last lookback_days.

    Searches only inside 'Meet Recordings' folders (where Google Meet saves all
    recordings automatically). Falls back to a name-based filter if no such
    folder exists. Results are ordered newest-first, capped at 100 files.

    Args:
        access_token: A valid Google access token with drive.readonly scope.
        lookback_days: How far back to look (default 60 days).

    Returns:
        List of DriveRecording objects. May be empty if none found.

    Raises:
        PermissionError: If the token is invalid or expired.
        httpx.HTTPStatusError: On other HTTP errors.
    """
    since = datetime.now(tz=UTC) - timedelta(days=lookback_days)
    since_str = since.strftime("%Y-%m-%dT%H:%M:%SZ")
    mime_clause = " or ".join(f"mimeType='{mt}'" for mt in _RECORDING_MIME_TYPES)

    async with httpx.AsyncClient(timeout=30.0) as client:
        folder_ids = await _get_meet_folder_ids(client, access_token)

        if folder_ids:
            # Restrict search to Meet Recordings folders
            parent_clause = " or ".join(f"'{fid}' in parents" for fid in folder_ids)
            query = f"({mime_clause}) and ({parent_clause}) and createdTime >= '{since_str}' and trashed=false"
        else:
            # No Meet Recordings folder yet — fall back to name pattern
            query = f"({mime_clause}) and name contains 'Meet' and createdTime >= '{since_str}' and trashed=false"

        params = {
            "q": query,
            "fields": "files(id,name,createdTime,size,mimeType)",
            "orderBy": "createdTime desc",
            "pageSize": "100",
        }

        response = await client.get(
            _DRIVE_FILES_URL,
            params=params,
            headers={"Authorization": f"Bearer {access_token}"},
        )

    if response.status_code == 401:
        raise PermissionError("Google access token is invalid or expired")
    response.raise_for_status()

    files: list[dict[str, Any]] = response.json().get("files", [])
    recordings: list[DriveRecording] = []
    for f in files:
        try:
            recordings.append(
                DriveRecording(
                    file_id=f["id"],
                    name=f["name"],
                    created_time=datetime.fromisoformat(f["createdTime"].replace("Z", "+00:00")),
                    size_bytes=int(f["size"]) if f.get("size") else None,
                    mime_type=f["mimeType"],
                )
            )
        except (KeyError, ValueError) as exc:
            logger.warning("Skipping malformed Drive file entry: %s", exc)

    logger.debug(
        "Drive listing: %d recordings found (lookback=%d days, folder_filter=%s)",
        len(recordings),
        lookback_days,
        bool(folder_ids),
    )
    return recordings


# ---------------------------------------------------------------------------
# Drive download (sync — used by Celery ingest task)
# ---------------------------------------------------------------------------


def download_recording_sync(access_token: str, file_id: str) -> bytes:
    """Download a Drive file to memory and return the raw bytes.

    IMPORTANT: The caller MUST delete the returned bytes object immediately
    after transcription. Audio is never written to disk or stored.

    Args:
        access_token: A valid Google access token with drive.readonly scope.
        file_id: The Google Drive file ID to download.

    Returns:
        Raw audio bytes.

    Raises:
        PermissionError: If the token is invalid or expired.
        httpx.HTTPStatusError: On other HTTP errors.
    """
    url = f"{_DRIVE_FILES_URL}/{file_id}?alt=media"
    with httpx.Client(timeout=300.0, follow_redirects=True) as client:
        response = client.get(
            url,
            headers={"Authorization": f"Bearer {access_token}"},
        )

    if response.status_code == 401:
        raise PermissionError("Google access token is invalid or expired for file download")
    response.raise_for_status()

    size = len(response.content)
    logger.info("Downloaded %d bytes for Drive file %s", size, file_id)
    return response.content
