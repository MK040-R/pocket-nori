"""
Calendar route — briefing context for today and tomorrow.

GET /calendar/today — dashboard context for the next two days.

Phase 4 implementation:
- refreshes Google Calendar access token using stored refresh token
- fetches today's upcoming events from Google Calendar

Phase 5 implementation:
- returns recent indexed meeting activity for dashboard context
- returns newly detected cross-meeting connections with deep-link conversation refs
"""

import logging
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from src.api.deps import get_current_user
from src.cache_utils import build_user_cache_key, get_cached_json, set_cached_json
from src.calendar_client import CalendarEvent, list_calendar_events
from src.database import get_client
from src.drive_client import refresh_access_token

logger = logging.getLogger(__name__)

router = APIRouter()
_TODAY_BRIEFING_CACHE_TTL_SECONDS = 60


class UpcomingMeeting(BaseModel):
    id: str
    title: str
    start_time: str
    attendees: list[str]


class OpenCommitment(BaseModel):
    id: str
    text: str
    owner: str
    due_date: str | None
    conversation_id: str
    conversation_title: str


class RecentActivity(BaseModel):
    conversation_id: str
    title: str
    meeting_date: str
    status: str


class RelatedConversation(BaseModel):
    conversation_id: str
    title: str
    meeting_date: str | None


class RecentConnection(BaseModel):
    id: str
    label: str
    summary: str
    linked_type: str
    created_at: str
    related_conversations: list[RelatedConversation]


class TodayBriefing(BaseModel):
    date: str
    upcoming_meetings: list[UpcomingMeeting]
    open_commitments: list[OpenCommitment]
    recent_activity: list[RecentActivity]
    recent_connections: list[RecentConnection]


def _get_google_tokens(db: Any, user_id: str) -> tuple[str, str]:
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
    access_token = row.get("google_access_token")
    refresh_token = row.get("google_refresh_token")

    if not isinstance(refresh_token, str) or not refresh_token.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Google Calendar access not authorised. "
                "Please sign out and sign in again to grant Calendar permission."
            ),
        )

    return str(access_token or ""), refresh_token


async def _load_calendar_events_with_refresh(
    db: Any,
    user_id: str,
    access_token: str,
    refresh_token: str,
    *,
    time_min: datetime,
    time_max: datetime,
) -> tuple[str, list[CalendarEvent]]:
    candidate_token = access_token.strip()
    if candidate_token:
        try:
            return candidate_token, await list_calendar_events(
                candidate_token,
                time_min=time_min,
                time_max=time_max,
            )
        except PermissionError:
            logger.info("Stored Google access token expired — refreshing for user=%s", user_id)

    try:
        refreshed_access_token = await refresh_access_token(refresh_token)
    except Exception as exc:
        raise PermissionError("Google Calendar access token refresh failed") from exc
    (
        db.table("user_index")
        .update({"google_access_token": refreshed_access_token})
        .eq("user_id", user_id)
        .execute()
    )
    events = await list_calendar_events(
        refreshed_access_token,
        time_min=time_min,
        time_max=time_max,
    )
    return refreshed_access_token, events


def _load_recent_activity(db: Any, user_id: str, limit: int = 8) -> list[RecentActivity]:
    rows = (
        db.table("conversations")
        .select("id, title, meeting_date, status")
        .eq("user_id", user_id)
        .eq("status", "indexed")
        .order("meeting_date", desc=True)
        .limit(limit)
        .execute()
    ).data or []

    return [
        RecentActivity(
            conversation_id=str(row.get("id", "")),
            title=str(row.get("title", "")),
            meeting_date=str(row.get("meeting_date", "")),
            status=str(row.get("status", "indexed")),
        )
        for row in rows
        if row.get("id")
    ]


def _load_recent_connections(db: Any, user_id: str, limit: int = 8) -> list[RecentConnection]:
    connection_rows = (
        db.table("connections")
        .select("id, label, summary, linked_type, created_at")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    ).data or []
    if not connection_rows:
        return []

    connection_ids = [str(row["id"]) for row in connection_rows if row.get("id")]
    if not connection_ids:
        return []

    linked_rows = (
        db.table("connection_linked_items")
        .select("connection_id, linked_id")
        .eq("user_id", user_id)
        .in_("connection_id", connection_ids)
        .execute()
    ).data or []

    linked_ids = {str(row["linked_id"]) for row in linked_rows if row.get("linked_id") is not None}
    conversation_by_id: dict[str, dict[str, Any]] = {}
    topic_to_conversation_id: dict[str, str] = {}

    if linked_ids:
        direct_conversation_rows = (
            db.table("conversations")
            .select("id, title, meeting_date")
            .eq("user_id", user_id)
            .in_("id", sorted(linked_ids))
            .execute()
        ).data or []
        conversation_by_id.update(
            {str(row["id"]): row for row in direct_conversation_rows if row.get("id") is not None}
        )

        unresolved_topic_ids = sorted(linked_ids - set(conversation_by_id.keys()))
        if unresolved_topic_ids:
            topic_rows = (
                db.table("topics")
                .select("id, conversation_id")
                .eq("user_id", user_id)
                .in_("id", unresolved_topic_ids)
                .execute()
            ).data or []
            topic_to_conversation_id = {
                str(row["id"]): str(row["conversation_id"])
                for row in topic_rows
                if row.get("id") and row.get("conversation_id")
            }
            topic_conversation_ids = sorted(set(topic_to_conversation_id.values()))
            unresolved_conversation_ids = [
                conversation_id
                for conversation_id in topic_conversation_ids
                if conversation_id not in conversation_by_id
            ]
            if unresolved_conversation_ids:
                topic_conversation_rows = (
                    db.table("conversations")
                    .select("id, title, meeting_date")
                    .eq("user_id", user_id)
                    .in_("id", unresolved_conversation_ids)
                    .execute()
                ).data or []
                conversation_by_id.update(
                    {
                        str(row["id"]): row
                        for row in topic_conversation_rows
                        if row.get("id") is not None
                    }
                )

    related_by_connection: dict[str, list[RelatedConversation]] = {}
    seen_pairs: set[tuple[str, str]] = set()
    for row in linked_rows:
        connection_id_value = row.get("connection_id")
        linked_id_value = row.get("linked_id")
        if connection_id_value is None or linked_id_value is None:
            continue
        connection_id = str(connection_id_value)
        linked_id = str(linked_id_value)
        conversation_id = linked_id
        if conversation_id not in conversation_by_id:
            conversation_id = topic_to_conversation_id.get(linked_id, "")
        conversation = conversation_by_id.get(conversation_id)
        if conversation is None:
            continue
        pair_key = (connection_id, conversation_id)
        if pair_key in seen_pairs:
            continue
        seen_pairs.add(pair_key)
        related_by_connection.setdefault(connection_id, []).append(
            RelatedConversation(
                conversation_id=conversation_id,
                title=str(conversation.get("title", "")),
                meeting_date=(
                    str(conversation["meeting_date"])
                    if conversation.get("meeting_date") is not None
                    else None
                ),
            )
        )

    return [
        RecentConnection(
            id=str(row.get("id", "")),
            label=str(row.get("label", "")),
            summary=str(row.get("summary", "")),
            linked_type=str(row.get("linked_type", "")),
            created_at=str(row.get("created_at", "")),
            related_conversations=related_by_connection.get(str(row.get("id", "")), [])[:3],
        )
        for row in connection_rows
        if row.get("id")
    ]


@router.get(
    "/today",
    response_model=TodayBriefing,
    summary="Briefing: upcoming meetings and open commitments for today and tomorrow",
)
async def get_today(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> TodayBriefing:
    """Return dashboard context for the next two days plus recent activity."""
    user_id: str = current_user["sub"]
    raw_jwt: str = current_user["_raw_jwt"]
    db = get_client(raw_jwt)
    today_start = datetime.combine(date.today(), time.min, tzinfo=UTC)
    today_end = today_start + timedelta(days=2)
    cache_key = build_user_cache_key(
        user_id,
        "today_briefing",
        {
            "date": today_start.date().isoformat(),
        },
    )
    cached = get_cached_json(cache_key)
    if cached is not None:
        return TodayBriefing.model_validate(cached)

    access_token, refresh_token = _get_google_tokens(db, user_id)

    try:
        _, today_events = await _load_calendar_events_with_refresh(
            db,
            user_id,
            access_token,
            refresh_token,
            time_min=today_start,
            time_max=today_end,
        )
    except Exception as exc:
        if isinstance(exc, PermissionError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Google Calendar access denied. Please sign in again.",
            ) from exc
        logger.error("Calendar read failed for user=%s: %s", user_id, type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to retrieve meetings from Google Calendar.",
        ) from exc

    now = datetime.now(tz=UTC)

    # Open commitments (most recently created, capped at 20)
    commitments_result = (
        db.table("commitments")
        .select("id, text, owner, due_date, conversation_id")
        .eq("user_id", user_id)
        .eq("status", "open")
        .order("created_at", desc=True)
        .limit(20)
        .execute()
    )
    commitments = commitments_result.data or []

    conv_titles: dict[str, str] = {}
    if commitments:
        conv_ids = list({c["conversation_id"] for c in commitments})
        convs_result = (
            db.table("conversations")
            .select("id, title")
            .eq("user_id", user_id)
            .in_("id", conv_ids)
            .execute()
        )
        conv_titles = {c["id"]: c["title"] for c in (convs_result.data or [])}

    recent_activity = _load_recent_activity(db, user_id)
    payload = TodayBriefing(
        date=date.today().isoformat(),
        upcoming_meetings=[
            UpcomingMeeting(
                id=event.event_id,
                title=event.title,
                start_time=event.start_time.isoformat(),
                attendees=event.attendees,
            )
            for event in today_events
            if event.start_time >= now
        ],
        open_commitments=[
            OpenCommitment(
                id=c["id"],
                text=c["text"],
                owner=c["owner"],
                due_date=c.get("due_date"),
                conversation_id=str(c["conversation_id"]),
                conversation_title=conv_titles.get(c["conversation_id"], ""),
            )
            for c in commitments
        ],
        recent_activity=recent_activity,
        recent_connections=[],
    )
    set_cached_json(
        cache_key,
        payload.model_dump(mode="json"),
        _TODAY_BRIEFING_CACHE_TTL_SECONDS,
    )
    return payload
