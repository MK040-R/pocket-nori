"""
Commitments routes.

GET  /commitments       — list all commitments across all conversations
POST /commitments       — manually create a commitment or follow-up
PATCH /commitments/{id} — mark a commitment as resolved (or re-open it)
"""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from src import llm_client
from src.api.deps import get_current_user
from src.cache_utils import (
    build_user_cache_key,
    bump_user_cache_version,
    get_cached_json,
    set_cached_json,
)
from src.database import get_client
from src.topic_node_store import TOPIC_NODE_FOREIGN_KEY_COLUMN, load_topic_node_label_map
from src.topic_utils import clean_topic_label

logger = logging.getLogger(__name__)

router = APIRouter()
_COMMITMENTS_CACHE_TTL_SECONDS = 60


# ---------------------------------------------------------------------------
# Response / request models
# ---------------------------------------------------------------------------


class CommitmentOut(BaseModel):
    id: str
    text: str
    owner: str
    due_date: str | None
    status: str
    action_type: str = "commitment"
    conversation_id: str
    conversation_title: str
    meeting_date: str | None = None
    topic_labels: list[str] = []


class CommitmentPatch(BaseModel):
    status: str  # "open" | "resolved"


class CommitmentCreate(BaseModel):
    text: str
    action_type: str = "commitment"  # "commitment" | "follow_up"
    owner: str = ""
    due_date: str | None = None


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
    topic_node_rows: list[dict[str, Any]],
) -> dict[str, list[str]]:
    if not topic_rows:
        return {}

    topic_node_map = {
        str(row["id"]): str(row.get("label") or "")
        for row in topic_node_rows
        if row.get("id")
    }
    conversation_labels: dict[str, list[str]] = {}
    for row in topic_rows:
        conversation_id = str(row.get("conversation_id") or "")
        if not conversation_id:
            continue
        topic_node_id = str(row.get(TOPIC_NODE_FOREIGN_KEY_COLUMN) or "")
        label = topic_node_map.get(topic_node_id) or clean_topic_label(str(row.get("label") or ""))
        if not label:
            continue
        conversation_labels.setdefault(conversation_id, [])
        if label not in conversation_labels[conversation_id]:
            conversation_labels[conversation_id].append(label)
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
    action_type: str | None = None,
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
    or ``resolved`` to filter by status. Optional ``action_type`` accepts
    ``commitment`` or ``follow_up``. Without filters, all items are returned.
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

    if action_type and action_type not in ("commitment", "follow_up"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="action_type must be 'commitment' or 'follow_up'",
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

    effective_topic = (topic or "").strip().lower()
    effective_meeting = (meeting or "").strip().lower()
    can_apply_window_in_db = (
        not effective_topic
        and not effective_meeting
        and meeting_date_from_parsed is None
        and meeting_date_to_parsed is None
    )
    cache_key = build_user_cache_key(
        user_id,
        "commitments_list",
        {
            "status": effective_filter,
            "action_type": action_type,
            "assignee": effective_assignee,
            "topic": effective_topic,
            "meeting": effective_meeting,
            "meeting_date_from": meeting_date_from,
            "meeting_date_to": meeting_date_to,
            "limit": limit,
            "offset": offset,
        },
    )
    cached = get_cached_json(cache_key)
    if cached is not None:
        return [CommitmentOut.model_validate(item) for item in cached]

    query = (
        db.table("commitments")
        .select("id, text, owner, due_date, status, action_type, conversation_id")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
    )
    if effective_filter == "open":
        query = query.eq("status", effective_filter)
    elif effective_filter == "resolved":
        query = query.or_("status.eq.resolved,status.eq.done,status.eq.cancelled")
    if action_type:
        query = query.eq("action_type", action_type)

    if effective_assignee:
        if effective_assignee.lower() == "me":
            email = str(current_user.get("email") or "").strip()
            if email:
                query = query.ilike("owner", f"%{email}%")
        else:
            query = query.ilike("owner", f"%{effective_assignee}%")
    if can_apply_window_in_db:
        query = query.range(offset, offset + limit - 1)

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
    topic_rows = (
        db.table("topics")
        .select(f"id, {TOPIC_NODE_FOREIGN_KEY_COLUMN}, label, conversation_id")
        .eq("user_id", user_id)
        .in_("conversation_id", conv_ids)
        .execute()
    ).data or []
    topic_node_ids = sorted(
        {
            str(row[TOPIC_NODE_FOREIGN_KEY_COLUMN])
            for row in topic_rows
            if row.get(TOPIC_NODE_FOREIGN_KEY_COLUMN) is not None
        }
    )
    topic_node_labels = load_topic_node_label_map(db, user_id, topic_node_ids)
    topic_node_rows = [
        {"id": node_id, "label": label} for node_id, label in topic_node_labels.items()
    ]
    topic_labels_by_conversation = _build_topic_labels_by_conversation(topic_rows, topic_node_rows)

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

    visible_rows = (
        filtered_rows if can_apply_window_in_db else filtered_rows[offset : offset + limit]
    )

    payload = [
        CommitmentOut(
            id=c["id"],
            text=c["text"],
            owner=c["owner"],
            due_date=c.get("due_date"),
            status=_normalize_commitment_status(c.get("status")),
            action_type=c.get("action_type") or "commitment",
            conversation_id=c["conversation_id"],
            conversation_title=str(c.get("conversation_title") or ""),
            meeting_date=c.get("meeting_date"),
            topic_labels=list(c.get("topic_labels") or []),
        )
        for c in visible_rows
    ]
    set_cached_json(
        cache_key,
        [item.model_dump(mode="json") for item in payload],
        _COMMITMENTS_CACHE_TTL_SECONDS,
    )
    return payload


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
        .select(f"id, {TOPIC_NODE_FOREIGN_KEY_COLUMN}, label, conversation_id")
        .eq("user_id", user_id)
        .eq("conversation_id", conversation_id)
        .execute()
    ).data or []
    topic_node_ids = sorted(
        {
            str(row[TOPIC_NODE_FOREIGN_KEY_COLUMN])
            for row in topic_rows
            if row.get(TOPIC_NODE_FOREIGN_KEY_COLUMN) is not None
        }
    )
    topic_node_labels = load_topic_node_label_map(db, user_id, topic_node_ids)
    topic_node_rows = [
        {"id": node_id, "label": label} for node_id, label in topic_node_labels.items()
    ]
    topic_labels = _build_topic_labels_by_conversation(
        topic_rows,
        topic_node_rows,
    ).get(conversation_id, [])

    logger.info(
        "Commitment %s status updated to %s — user=%s",
        commitment_id,
        body.status,
        user_id,
    )
    bump_user_cache_version(user_id)

    return CommitmentOut(
        id=updated["id"],
        text=updated["text"],
        owner=updated["owner"],
        due_date=updated.get("due_date"),
        status=_normalize_commitment_status(updated.get("status")),
        action_type=updated.get("action_type") or "commitment",
        conversation_id=conversation_id,
        conversation_title=str(conversation.get("title") or ""),
        meeting_date=(
            str(conversation["meeting_date"])
            if conversation.get("meeting_date") is not None
            else None
        ),
        topic_labels=topic_labels,
    )


# ---------------------------------------------------------------------------
# POST /commitments  — manual creation
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=CommitmentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Manually create a commitment or follow-up",
)
def create_commitment(
    body: CommitmentCreate,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> CommitmentOut:
    """Create a commitment or follow-up manually (not AI-extracted).

    The item is not linked to any specific conversation — ``conversation_id``
    will be empty and ``conversation_title`` will be an empty string.
    """
    user_id: str = current_user["sub"]
    raw_jwt: str = current_user["_raw_jwt"]
    db = get_client(raw_jwt)

    if not body.text or not body.text.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="text is required",
        )
    if body.action_type not in ("commitment", "follow_up"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="action_type must be 'commitment' or 'follow_up'",
        )

    new_id = str(uuid.uuid4())
    due_date: str | None = None
    if body.due_date:
        parsed_due = _parse_iso_timestamp(body.due_date)
        if parsed_due is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="due_date must be a valid ISO timestamp",
            )
        due_date = parsed_due.isoformat()

    insert_result = (
        db.table("commitments")
        .insert(
            {
                "id": new_id,
                "user_id": user_id,
                "conversation_id": None,
                "text": body.text.strip(),
                "owner": body.owner.strip() if body.owner else "",
                "due_date": due_date,
                "status": "open",
                "action_type": body.action_type,
            }
        )
        .execute()
    )

    if not insert_result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create commitment",
        )

    created = insert_result.data[0]
    existing_index = (
        db.table("user_index")
        .select("commitment_count")
        .eq("user_id", user_id)
        .execute()
    )
    if existing_index.data:
        current_commitment_count = int(existing_index.data[0].get("commitment_count") or 0)
        db.table("user_index").update(
            {
                "commitment_count": current_commitment_count + 1,
                "last_updated": datetime.now(tz=UTC).isoformat(),
            }
        ).eq("user_id", user_id).execute()
    bump_user_cache_version(user_id)
    logger.info("Manual commitment created — id=%s user=%s", new_id, user_id)

    return CommitmentOut(
        id=created["id"],
        text=created["text"],
        owner=created.get("owner") or "",
        due_date=created.get("due_date"),
        status="open",
        action_type=created.get("action_type") or "commitment",
        conversation_id=str(created.get("conversation_id") or ""),
        conversation_title="",
        meeting_date=None,
        topic_labels=[],
    )


# ---------------------------------------------------------------------------
# POST /commitments/{id}/draft — generate draft email/message
# ---------------------------------------------------------------------------


class DraftRequest(BaseModel):
    format: Literal["email", "message"] = Field(default="email", description="'email' or 'message'")


class DraftResponse(BaseModel):
    subject: str
    body: str
    recipient_suggestion: str
    commitment_text: str
    format: str


@router.post(
    "/{commitment_id}/draft",
    response_model=DraftResponse,
    summary="Generate a draft email or message from a commitment",
)
def draft_from_commitment(
    commitment_id: str,
    body: DraftRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> DraftResponse:
    """Generate a draft email or message based on a commitment and its meeting context.

    Uses linked transcript segments for context. Returns a structured draft
    with subject, body, and suggested recipient.
    """
    user_id: str = current_user["sub"]
    raw_jwt: str = current_user["_raw_jwt"]
    db = get_client(raw_jwt)

    if body.format not in ("email", "message"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="format must be 'email' or 'message'",
        )

    # --- Look up commitment ---
    commitment_rows = (
        db.table("commitments")
        .select("id, text, owner, conversation_id, action_type")
        .eq("id", commitment_id)
        .eq("user_id", user_id)
        .execute()
    ).data or []

    if not commitment_rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Commitment not found",
        )

    commitment = commitment_rows[0]
    conversation_id = str(commitment.get("conversation_id") or "")

    # --- Fetch conversation context ---
    meeting_title = ""
    meeting_date = ""
    if conversation_id:
        conv_rows = (
            db.table("conversations")
            .select("title, meeting_date")
            .eq("id", conversation_id)
            .eq("user_id", user_id)
            .execute()
        ).data or []
        if conv_rows:
            meeting_title = str(conv_rows[0].get("title") or "")
            meeting_date = str(conv_rows[0].get("meeting_date") or "")

    # --- Fetch linked transcript segments for context ---
    transcript_context = ""
    if conversation_id:
        segment_link_rows = (
            db.table("commitment_segment_links")
            .select("segment_id")
            .eq("commitment_id", commitment_id)
            .eq("user_id", user_id)
            .limit(10)
            .execute()
        ).data or []

        segment_ids = [str(row["segment_id"]) for row in segment_link_rows if row.get("segment_id")]
        if segment_ids:
            segment_rows = (
                db.table("transcript_segments")
                .select("speaker_id, text")
                .eq("user_id", user_id)
                .in_("id", segment_ids)
                .order("start_ms")
                .execute()
            ).data or []
            transcript_context = "\n".join(
                f"[{seg.get('speaker_id', '')}] {seg.get('text', '')}" for seg in segment_rows
            )

    # --- Generate draft via LLM ---
    try:
        result = llm_client.generate_commitment_draft(
            commitment_text=str(commitment.get("text", "")),
            owner=str(commitment.get("owner", "")),
            meeting_title=meeting_title,
            meeting_date=meeting_date,
            transcript_context=transcript_context,
            format=body.format,
        )
    except Exception as exc:
        logger.error(
            "Draft generation failed — commitment=%s user=%s error=%s",
            commitment_id,
            user_id,
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Draft generation temporarily unavailable.",
        ) from exc

    logger.info(
        "Draft generated — commitment=%s format=%s user=%s", commitment_id, body.format, user_id
    )

    return DraftResponse(
        subject=result.subject,
        body=result.body,
        recipient_suggestion=result.recipient_suggestion,
        commitment_text=str(commitment.get("text", "")),
        format=body.format,
    )
