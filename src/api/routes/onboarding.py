"""
Onboarding routes — Google Drive recording import flow.

Endpoints:
  GET  /onboarding/available-recordings  — lists Drive recordings not yet imported
  POST /onboarding/import                — starts ingest jobs for selected recordings
  GET  /onboarding/import/status/{job_id} — polls the status of a single ingest job
"""

import logging
from typing import Any

from celery.result import AsyncResult
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from src.api.deps import get_current_user
from src.database import get_client
from src.drive_client import DriveRecording, list_meet_recordings, refresh_access_token
from src.workers.ingest import celery_app, ingest_recording

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class AvailableRecording(BaseModel):
    file_id: str
    name: str
    created_time: str  # ISO-8601
    size_bytes: int | None
    mime_type: str
    already_imported: bool


class ImportRequest(BaseModel):
    file_ids: list[str]


class ImportJob(BaseModel):
    file_id: str
    job_id: str


class ImportResponse(BaseModel):
    jobs: list[ImportJob]


class JobStatus(BaseModel):
    job_id: str
    status: str   # pending | progress | success | failure
    detail: str | None = None
    result: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_google_tokens(db: Any, user_id: str) -> tuple[str, str]:
    """Retrieve stored Google tokens for the user.

    Returns (google_access_token, google_refresh_token).
    Raises HTTP 400 if the tokens are missing (user must re-authenticate).
    """
    rows = (
        db.table("user_index")
        .select("google_access_token, google_refresh_token")
        .eq("user_id", user_id)
        .execute()
    )
    if not rows.data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User index not found. Please sign in again.",
        )
    row = rows.data[0]
    access_token: str | None = row.get("google_access_token")
    refresh_token: str | None = row.get("google_refresh_token")

    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Google Drive access not authorised. "
                "Please sign out and sign in again to grant Drive permission."
            ),
        )
    return access_token or "", refresh_token


# ---------------------------------------------------------------------------
# GET /onboarding/available-recordings
# ---------------------------------------------------------------------------


@router.get(
    "/available-recordings",
    response_model=list[AvailableRecording],
    summary="List Drive recordings available to import",
)
async def available_recordings(
    lookback_days: int = 60,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> list[AvailableRecording]:
    """Return Google Drive video files from the last lookback_days, annotated
    with whether each has already been imported into Farz.

    The client should call this first to show the user what's available.
    """
    user_id: str = current_user["sub"]
    raw_jwt: str = current_user["_raw_jwt"]
    db = get_client(raw_jwt)

    access_token, refresh_token = _get_google_tokens(db, user_id)

    # Refresh the access token — it may have expired since last login
    try:
        access_token = await refresh_access_token(refresh_token)
    except Exception as exc:
        logger.error("Google token refresh failed for user=%s: %s", user_id, type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to refresh Google access. Please sign in again.",
        ) from exc

    # Also store the refreshed access token for subsequent calls
    db.table("user_index").update({"google_access_token": access_token}).eq(
        "user_id", user_id
    ).execute()

    # Fetch Drive recordings
    try:
        drive_recordings: list[DriveRecording] = await list_meet_recordings(
            access_token, lookback_days=lookback_days
        )
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google Drive access denied. Please sign in again.",
        ) from exc
    except Exception as exc:
        logger.error("Drive listing failed for user=%s: %s", user_id, type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to retrieve recordings from Google Drive.",
        ) from exc

    if not drive_recordings:
        return []

    # Check which Drive file IDs are already imported
    drive_ids = [r.file_id for r in drive_recordings]
    imported_result = (
        db.table("conversations")
        .select("drive_file_id")
        .eq("user_id", user_id)
        .in_("drive_file_id", drive_ids)
        .execute()
    )
    imported_ids: set[str] = {
        row["drive_file_id"]
        for row in (imported_result.data or [])
        if row.get("drive_file_id")
    }

    return [
        AvailableRecording(
            file_id=r.file_id,
            name=r.name,
            created_time=r.created_time.isoformat(),
            size_bytes=r.size_bytes,
            mime_type=r.mime_type,
            already_imported=r.file_id in imported_ids,
        )
        for r in drive_recordings
    ]


# ---------------------------------------------------------------------------
# POST /onboarding/import
# ---------------------------------------------------------------------------


@router.post(
    "/import",
    response_model=ImportResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start ingest jobs for selected Drive recordings",
)
async def start_import(
    body: ImportRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> ImportResponse:
    """Queue ingest_recording Celery tasks for each requested file_id.

    Returns a list of (file_id, job_id) pairs. Poll
    GET /onboarding/import/status/{job_id} to track progress.
    """
    if not body.file_ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="file_ids must not be empty",
        )
    if len(body.file_ids) > 20:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Maximum 20 recordings per import batch",
        )

    user_id: str = current_user["sub"]
    raw_jwt: str = current_user["_raw_jwt"]
    db = get_client(raw_jwt)

    _, refresh_token = _get_google_tokens(db, user_id)

    # Fetch Drive metadata for the requested files in one call
    try:
        all_drive = await list_meet_recordings(
            await refresh_access_token(refresh_token), lookback_days=120
        )
    except Exception as exc:
        logger.error("Drive listing failed during import for user=%s: %s", user_id, type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to retrieve file metadata from Google Drive.",
        ) from exc

    drive_by_id = {r.file_id: r for r in all_drive}

    jobs: list[ImportJob] = []
    for file_id in body.file_ids:
        recording = drive_by_id.get(file_id)
        if recording is None:
            logger.warning("File %s not found in Drive for user=%s — skipping", file_id, user_id)
            continue

        task = ingest_recording.delay(
            drive_file_id=recording.file_id,
            file_name=recording.name,
            created_time_iso=recording.created_time.isoformat(),
            mime_type=recording.mime_type,
            user_id=user_id,
            user_jwt=raw_jwt,
            google_refresh_token=refresh_token,
        )
        jobs.append(ImportJob(file_id=file_id, job_id=task.id))
        logger.info("Queued ingest job %s for file %s user %s", task.id, file_id, user_id)

    if not jobs:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="None of the requested file_ids were found in your Google Drive.",
        )

    return ImportResponse(jobs=jobs)


# ---------------------------------------------------------------------------
# GET /onboarding/import/status/{job_id}
# ---------------------------------------------------------------------------


@router.get(
    "/import/status/{job_id}",
    response_model=JobStatus,
    summary="Poll the status of an ingest job",
)
def import_status(
    job_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> JobStatus:
    """Return the current status of a Celery ingest job.

    Status values:
    - pending   — job is queued, not yet started
    - progress  — job is running (detail shows current step)
    - success   — job completed; result contains conversation_id and segment_count
    - failure   — job failed; detail contains the error message
    """
    result = AsyncResult(job_id, app=celery_app)
    state = result.state.lower()

    if state == "pending":
        return JobStatus(job_id=job_id, status="pending")

    if state == "progress":
        meta = result.info or {}
        return JobStatus(
            job_id=job_id,
            status="progress",
            detail=meta.get("status", "processing"),
        )

    if state == "success":
        return JobStatus(
            job_id=job_id,
            status="success",
            result=result.result if isinstance(result.result, dict) else {},
        )

    # failure or revoked
    error_detail: str = str(result.result) if result.result else "Unknown error"
    return JobStatus(job_id=job_id, status="failure", detail=error_detail)
