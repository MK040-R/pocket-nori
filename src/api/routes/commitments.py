"""
Commitments routes.

GET  /commitments       — list all commitments across all conversations
PATCH /commitments/{id} — mark a commitment as resolved (or re-open it)
"""

import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from src.api.deps import get_current_user
from src.database import get_client
from src.topic_utils import cluster_topic_rows

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Response / request models
# ---------------------------------------------------------------------------


class CommitmentOut(BaseModel):
    id: str
    text: str
    owner: str
    due_date: str | None
    status: str
    conversation_id: str
    conversation_title: str
    meeting_date: str | None = None
    topic_labels: list[str] = []


class CommitmentPatch(BaseModel):
    status: str  # "open" | "resolved"


def _normalize_commitment_status(value: str | None) -> str:
    if value == "open":
        return "open"
    return "resolved"


def _parse_iso_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    candidate = value.strip()
    if "T" in candidate and "+" not in candidate and candidate.count(" ") == 1:
        candidate = candidate.replace(" ", "+", 1)
    try:
        parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _build_topic_labels_by_conversation(
    topic_rows: list[dict[str, Any]],
    conversation_dates: dict[str, str | None],
) -> dict[str, list[str]]:
    if not topic_rows:
        return {}

    enriched_rows = [
        {
            **row,
            "meeting_date": conversation_dates.get(str(row.get("conversation_id") or "")),
        }
        for row in topic_rows
    ]
    conversation_labels: dict[str, list[str]] = {}
    for cluster in cluster_topic_rows(enriched_rows):
        for conversation_id in cluster.conversation_ids:
            conversation_labels.setdefault(conversation_id, [])
            if cluster.label not in conversation_labels[conversation_id]:
                conversation_labels[conversation_id].append(cluster.label)
    return conversation_labels


# ---------------------------------------------------------------------------
# GET /commitments
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=list[CommitmentOut],
    summary="List all commitments across all conversations",
)
def list_commitments(
    filter_status: str | None = None,
    status_param: str | None = Query(default=None, alias="status"),
    assignee: str | None = None,
    attributed_to: str | None = Query(default=None, alias="attributed_to"),
    topic: str | None = None,
    meeting: str | None = None,
    meeting_date_from: str | None = None,
    meeting_date_to: str | None = None,
    limit: int = 100,
    offset: int = 0,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> list[CommitmentOut]:
    """Return all commitments for the current user.

    Optional query parameter ``filter_status`` or ``status`` accepts ``open``
    or ``resolved`` to filter by status. Without it, all commitments are returned.
    """
    user_id: str = current_user["sub"]
    raw_jwt: str = current_user["_raw_jwt"]
    db = get_client(raw_jwt)

    effective_filter = filter_status or status_param
    if effective_filter and effective_filter not in ("open", "resolved"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="status filter must be 'open' or 'resolved'",
        )

    effective_assignee = (assignee or attributed_to or "").strip()
    if assignee and attributed_to and assignee.strip().lower() != attributed_to.strip().lower():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="assignee and attributed_to must match when both are provided",
        )

    meeting_date_from_parsed = _parse_iso_timestamp(meeting_date_from)
    meeting_date_to_parsed = _parse_iso_timestamp(meeting_date_to)
    if meeting_date_from and meeting_date_from_parsed is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="meeting_date_from must be a valid ISO timestamp",
        )
    if meeting_date_to and meeting_date_to_parsed is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="meeting_date_to must be a valid ISO timestamp",
        )
    if (
        meeting_date_from_parsed is not None
        and meeting_date_to_parsed is not None
        and meeting_date_from_parsed > meeting_date_to_parsed
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="meeting_date_from must be before or equal to meeting_date_to",
        )

    query = (
        db.table("commitments")
        .select("id, text, owner, due_date, status, conversation_id")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
    )
    if effective_filter == "open":
        query = query.eq("status", effective_filter)
    elif effective_filter == "resolved":
        query = query.or_("status.eq.resolved,status.eq.done,status.eq.cancelled")

    if effective_assignee:
        if effective_assignee.lower() == "me":
            email = str(current_user.get("email") or "").strip()
            if email:
                query = query.ilike("owner", f"%{email}%")
        else:
            query = query.ilike("owner", f"%{effective_assignee}%")

    result = query.execute()
    commitments = result.data or []
    if not commitments:
        return []

    # Fetch conversation titles + dates
    conv_ids = list({c["conversation_id"] for c in commitments})
    convs_result = (
        db.table("conversations")
        .select("id, title, meeting_date")
        .eq("user_id", user_id)
        .in_("id", conv_ids)
        .execute()
    )
    conv_rows = convs_result.data or []
    conv_map = {str(c["id"]): c for c in conv_rows if c.get("id")}
    conversation_dates = {
        str(c["id"]): c.get("meeting_date") for c in conv_rows if c.get("id") is not None
    }

    topic_rows = (
        db.table("topics")
        .select("id, label, summary, status, key_quotes, conversation_id, created_at")
        .eq("user_id", user_id)
        .in_("conversation_id", conv_ids)
        .execute()
    ).data or []
    topic_labels_by_conversation = _build_topic_labels_by_conversation(
        topic_rows, conversation_dates
    )

    effective_topic = (topic or "").strip().lower()
    effective_meeting = (meeting or "").strip().lower()

    filtered_rows: list[dict[str, Any]] = []
    for commitment in commitments:
        conversation_id = str(commitment.get("conversation_id") or "")
        conversation = conv_map.get(conversation_id, {})
        conversation_title = str(conversation.get("title") or "")
        meeting_date_value = (
            str(conversation.get("meeting_date"))
            if conversation.get("meeting_date") is not None
            else None
        )
        topic_labels = topic_labels_by_conversation.get(conversation_id, [])

        if effective_meeting and effective_meeting not in conversation_title.lower():
            continue
        if effective_topic and not any(effective_topic in label.lower() for label in topic_labels):
            continue
        parsed_meeting_date = _parse_iso_timestamp(meeting_date_value)
        if meeting_date_from_parsed and (
            parsed_meeting_date is None or parsed_meeting_date < meeting_date_from_parsed
        ):
            continue
        if meeting_date_to_parsed and (
            parsed_meeting_date is None or parsed_meeting_date > meeting_date_to_parsed
        ):
            continue

        filtered_rows.append(
            {
                **commitment,
                "conversation_title": conversation_title,
                "meeting_date": meeting_date_value,
                "topic_labels": topic_labels,
            }
        )

    visible_rows = filtered_rows[offset : offset + limit]

    return [
        CommitmentOut(
            id=c["id"],
            text=c["text"],
            owner=c["owner"],
            due_date=c.get("due_date"),
            status=_normalize_commitment_status(c.get("status")),
            conversation_id=c["conversation_id"],
            conversation_title=str(c.get("conversation_title") or ""),
            meeting_date=c.get("meeting_date"),
            topic_labels=list(c.get("topic_labels") or []),
        )
        for c in visible_rows
    ]


# ---------------------------------------------------------------------------
# PATCH /commitments/{id}
# ---------------------------------------------------------------------------


@router.patch(
    "/{commitment_id}",
    response_model=CommitmentOut,
    summary="Update the status of a commitment",
)
def update_commitment(
    commitment_id: str,
    body: CommitmentPatch,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> CommitmentOut:
    """Update a commitment's status to 'resolved' or back to 'open'.

    Only the status field can be patched — text, owner, and due_date are
    immutable once created.
    """
    user_id: str = current_user["sub"]
    raw_jwt: str = current_user["_raw_jwt"]
    db = get_client(raw_jwt)

    if body.status not in ("open", "resolved"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="status must be 'open' or 'resolved'",
        )

    # Verify ownership before updating
    existing = (
        db.table("commitments")
        .select("id")
        .eq("id", commitment_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not existing.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Commitment not found")

    storage_statuses = [body.status]
    if body.status == "resolved":
        # Backward compatibility for older DBs that still allow `done`.
        storage_statuses.append("done")

    update_result_data: list[dict[str, Any]] = []
    last_error: Exception | None = None
    for storage_status in storage_statuses:
        try:
            update_result = (
                db.table("commitments")
                .update({"status": storage_status})
                .eq("id", commitment_id)
                .eq("user_id", user_id)
                .execute()
            )
        except Exception as exc:  # pragma: no cover - only triggered with DB constraint mismatch
            last_error = exc
            continue
        update_result_data = update_result.data or []
        if update_result_data:
            break

    if not update_result_data and last_error is not None:
        logger.error(
            "Commitment status update failed — commitment=%s user=%s error=%s",
            commitment_id,
            user_id,
            type(last_error).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update commitment status",
        )

    if not update_result_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Commitment not found or update failed",
        )
    updated = update_result_data[0]

    # Fetch conversation title
    conversation_id = str(updated.get("conversation_id") or "")
    conv_result = (
        db.table("conversations")
        .select("id, title, meeting_date")
        .eq("id", conversation_id)
        .eq("user_id", user_id)
        .execute()
    )
    conversation = conv_result.data[0] if conv_result.data else {}

    topic_rows = (
        db.table("topics")
        .select("id, label, summary, status, key_quotes, conversation_id, created_at")
        .eq("user_id", user_id)
        .eq("conversation_id", conversation_id)
        .execute()
    ).data or []
    topic_labels = _build_topic_labels_by_conversation(
        topic_rows,
        {conversation_id: conversation.get("meeting_date")},
    ).get(conversation_id, [])

    logger.info(
        "Commitment %s status updated to %s — user=%s",
        commitment_id,
        body.status,
        user_id,
    )

    return CommitmentOut(
        id=updated["id"],
        text=updated["text"],
        owner=updated["owner"],
        due_date=updated.get("due_date"),
        status=_normalize_commitment_status(updated.get("status")),
        conversation_id=conversation_id,
        conversation_title=str(conversation.get("title") or ""),
        meeting_date=(
            str(conversation["meeting_date"])
            if conversation.get("meeting_date") is not None
            else None
        ),
        topic_labels=topic_labels,
    )
