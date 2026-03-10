"""
Commitments routes.

GET  /commitments       — list all commitments across all conversations
PATCH /commitments/{id} — mark a commitment as resolved (or re-open it)
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from src.api.deps import get_current_user
from src.database import get_client

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


class CommitmentPatch(BaseModel):
    status: str  # "open" | "resolved"


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
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="status filter must be 'open' or 'resolved'",
        )

    query = (
        db.table("commitments")
        .select("id, text, owner, due_date, status, conversation_id")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
    )
    if effective_filter:
        query = query.eq("status", effective_filter)

    result = query.range(offset, offset + limit - 1).execute()
    commitments = result.data or []
    if not commitments:
        return []

    # Fetch conversation titles
    conv_ids = list({c["conversation_id"] for c in commitments})
    convs_result = (
        db.table("conversations")
        .select("id, title")
        .eq("user_id", user_id)
        .in_("id", conv_ids)
        .execute()
    )
    conv_map = {c["id"]: c["title"] for c in (convs_result.data or [])}

    return [
        CommitmentOut(
            id=c["id"],
            text=c["text"],
            owner=c["owner"],
            due_date=c.get("due_date"),
            status=c["status"],
            conversation_id=c["conversation_id"],
            conversation_title=conv_map.get(c["conversation_id"], ""),
        )
        for c in commitments
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
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
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

    update_result = (
        db.table("commitments")
        .update({"status": body.status})
        .eq("id", commitment_id)
        .eq("user_id", user_id)
        .execute()
    )

    if not update_result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Commitment not found or update failed",
        )
    updated = update_result.data[0]

    # Fetch conversation title
    conv_result = (
        db.table("conversations")
        .select("id, title")
        .eq("id", updated.get("conversation_id", ""))
        .eq("user_id", user_id)
        .execute()
    )
    conv_title = conv_result.data[0]["title"] if conv_result.data else ""

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
        status=updated["status"],
        conversation_id=updated["conversation_id"],
        conversation_title=conv_title,
    )
