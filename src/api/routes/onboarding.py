"""
Onboarding routes — Google Meet transcript import flow.

Endpoints:
  GET  /onboarding/available-recordings      — lists Drive transcripts not yet imported
  POST /onboarding/import                    — starts ingest jobs for selected transcripts
  GET  /onboarding/import/status             — aggregate status across all active jobs
  GET  /onboarding/import/status/{job_id}    — polls the status of a single ingest job
"""

import logging
from typing import Any

from celery.result import AsyncResult
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from src.api.deps import get_current_user
from src.database import get_client
from src.drive_client import DriveTranscript, list_meet_transcripts, refresh_access_token
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
    file_id: str | None = None
    status: str  # pending | progress | success | failure
    detail: str | None = None
    result: dict[str, Any] | None = None


class AggregateImportStatus(BaseModel):
    total: int
    pending: int
    processing: int
    succeeded: int
    failed: int
    jobs: list[JobStatus]


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
    summary="List Google Meet transcripts available to import",
)
async def available_recordings(
    lookback_days: int = 365,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> list[AvailableRecording]:
    """Return Google Meet transcript documents from the last lookback_days,
    annotated with whether each has already been imported into Pocket Nori.
    """
    user_id: str = current_user["sub"]
    raw_jwt: str = current_user["_raw_jwt"]
    db = get_client(raw_jwt)

    access_token, refresh_token = _get_google_tokens(db, user_id)

    try:
        access_token = await refresh_access_token(refresh_token)
    except Exception as exc:
        logger.error("Google token refresh failed for user=%s: %s", user_id, type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to refresh Google access. Please sign in again.",
        ) from exc

    db.table("user_index").update({"google_access_token": access_token}).eq(
        "user_id", user_id
    ).execute()

    try:
        transcripts: list[DriveTranscript] = await list_meet_transcripts(
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
            detail="Failed to retrieve transcripts from Google Drive.",
        ) from exc

    if not transcripts:
        return []

    drive_ids = [t.file_id for t in transcripts]
    imported_result = (
        db.table("conversations")
        .select("drive_file_id")
        .eq("user_id", user_id)
        .in_("drive_file_id", drive_ids)
        .execute()
    )
    imported_ids: set[str] = {
        row["drive_file_id"] for row in (imported_result.data or []) if row.get("drive_file_id")
    }

    return [
        AvailableRecording(
            file_id=t.file_id,
            name=t.name,
            created_time=t.created_time.isoformat(),
            size_bytes=t.size_bytes,
            already_imported=t.file_id in imported_ids,
        )
        for t in transcripts
    ]


# ---------------------------------------------------------------------------
# POST /onboarding/import
# ---------------------------------------------------------------------------


@router.post(
    "/import",
    response_model=ImportResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start ingest jobs for selected transcript documents",
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
            detail="Maximum 20 transcripts per import batch",
        )

    user_id: str = current_user["sub"]
    raw_jwt: str = current_user["_raw_jwt"]
    db = get_client(raw_jwt)

    _, refresh_token = _get_google_tokens(db, user_id)

    try:
        all_transcripts = await list_meet_transcripts(
            await refresh_access_token(refresh_token), lookback_days=365
        )
    except Exception as exc:
        logger.error(
            "Drive listing failed during import for user=%s: %s",
            user_id,
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to retrieve transcript metadata from Google Drive.",
        ) from exc

    transcript_by_id = {t.file_id: t for t in all_transcripts}

    jobs: list[ImportJob] = []
    for file_id in body.file_ids:
        transcript = transcript_by_id.get(file_id)
        if transcript is None:
            logger.warning("File %s not found in Drive for user=%s — skipping", file_id, user_id)
            continue

        task = ingest_recording.delay(
            drive_file_id=transcript.file_id,
            file_name=transcript.name,
            created_time_iso=transcript.created_time.isoformat(),
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
# GET /onboarding/import/status  — user-level aggregate
# ---------------------------------------------------------------------------


@router.get(
    "/import/status",
    response_model=AggregateImportStatus,
    summary="Get aggregate import status for the current user's active jobs",
)
def import_status_aggregate(
    job_ids: str = "",
    file_ids: str = "",
    current_user: dict[str, Any] = Depends(get_current_user),
) -> AggregateImportStatus:
    """Return aggregate status across a comma-separated list of job IDs.

    Pass the job IDs returned by POST /import as a comma-separated query
    parameter: ``?job_ids=id1,id2,id3&file_ids=fid1,fid2,fid3``

    Returns per-job status plus summary counts.
    """
    if not job_ids.strip():
        return AggregateImportStatus(
            total=0, pending=0, processing=0, succeeded=0, failed=0, jobs=[]
        )

    user_id: str = current_user["sub"]
    ids = [j.strip() for j in job_ids.split(",") if j.strip()]
    fids = [f.strip() for f in file_ids.split(",") if f.strip()]
    # Pad file_ids list to match job_ids length (None for unmatched positions)
    fid_map: dict[str, str | None] = {
        ids[i]: fids[i] if i < len(fids) else None for i in range(len(ids))
    }

    job_statuses: list[JobStatus] = []
    counts = {"pending": 0, "processing": 0, "succeeded": 0, "failed": 0}

    for job_id in ids:
        result = AsyncResult(job_id, app=celery_app)
        state = result.state.lower()
        file_id = fid_map.get(job_id)

        if state == "pending":
            js = JobStatus(job_id=job_id, file_id=file_id, status="pending")
            counts["pending"] += 1
        elif state == "progress":
            meta = result.info or {}
            if meta.get("user_id") and meta["user_id"] != user_id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Job not found")
            js = JobStatus(
                job_id=job_id,
                file_id=file_id,
                status="progress",
                detail=meta.get("status", "processing"),
            )
            counts["processing"] += 1
        elif state == "success":
            task_result: dict[str, Any] = result.result if isinstance(result.result, dict) else {}
            if task_result.get("user_id") and task_result["user_id"] != user_id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Job not found")
            js = JobStatus(
                job_id=job_id,
                file_id=file_id or task_result.get("drive_file_id"),
                status="success",
                result=task_result,
            )
            counts["succeeded"] += 1
        else:
            error_detail: str = str(result.result) if result.result else "Unknown error"
            js = JobStatus(job_id=job_id, file_id=file_id, status="failure", detail=error_detail)
            counts["failed"] += 1

        job_statuses.append(js)

    return AggregateImportStatus(
        total=len(ids),
        pending=counts["pending"],
        processing=counts["processing"],
        succeeded=counts["succeeded"],
        failed=counts["failed"],
        jobs=job_statuses,
    )


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
    user_id: str = current_user["sub"]
    result = AsyncResult(job_id, app=celery_app)
    state = result.state.lower()

    if state == "pending":
        return JobStatus(job_id=job_id, status="pending")

    if state == "progress":
        meta = result.info or {}
        if meta.get("user_id") and meta["user_id"] != user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Job not found")
        return JobStatus(
            job_id=job_id,
            status="progress",
            detail=meta.get("status", "processing"),
        )

    if state == "success":
        task_result: dict[str, Any] = result.result if isinstance(result.result, dict) else {}
        if task_result.get("user_id") and task_result["user_id"] != user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Job not found")
        return JobStatus(
            job_id=job_id,
            file_id=task_result.get("drive_file_id"),
            status="success",
            result=task_result,
        )

    # failure or revoked
    error_detail: str = str(result.result) if result.result else "Unknown error"
    return JobStatus(job_id=job_id, status="failure", detail=error_detail)
