"""
Calendar route — today's briefing context.

GET /calendar/today — dashboard context for today.

Phase 4 implementation:
- refreshes Google Calendar access token using stored refresh token
- fetches today's upcoming events from Google Calendar
- links imported conversations to calendar events by meeting-time proximity
- triggers recurring brief scheduling for eligible upcoming recurring meetings

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
from src.calendar_client import CalendarEvent, list_calendar_events
from src.database import get_client
from src.drive_client import refresh_access_token
from src.workers.tasks import schedule_recurring_briefs

logger = logging.getLogger(__name__)

router = APIRouter()

_MATCH_WINDOW_SECONDS = 8 * 60 * 60
_CALENDAR_LINK_LOOKBACK_DAYS = 365
_CALENDAR_LINK_LOOKAHEAD_DAYS = 30


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


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


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


def _best_match_event(
    conversation_time: datetime,
    events: list[CalendarEvent],
    used_event_ids: set[str],
) -> CalendarEvent | None:
    best: tuple[float, CalendarEvent] | None = None
    for event in events:
        if event.event_id in used_event_ids:
            continue
        distance_seconds = abs((conversation_time - event.start_time).total_seconds())
        if distance_seconds > _MATCH_WINDOW_SECONDS:
            continue
        if best is None or distance_seconds < best[0]:
            best = (distance_seconds, event)
    return best[1] if best else None


def _sync_conversation_calendar_links(
    db: Any,
    user_id: str,
    conversations: list[dict[str, Any]],
    events: list[CalendarEvent],
) -> int:
    if not conversations or not events:
        return 0

    parsed_conversations: list[tuple[str, datetime]] = []
    for row in conversations:
        conversation_id = row.get("id")
        if not isinstance(conversation_id, str) or not conversation_id.strip():
            continue
        meeting_date = _parse_datetime(row.get("meeting_date"))
        if meeting_date is None:
            continue
        parsed_conversations.append((conversation_id, meeting_date))

    parsed_conversations.sort(key=lambda item: item[1])

    linked_count = 0
    used_event_ids: set[str] = set()
    for conversation_id, meeting_date in parsed_conversations:
        match = _best_match_event(meeting_date, events, used_event_ids)
        if match is None:
            continue

        (
            db.table("conversations")
            .update({"calendar_event_id": match.event_id})
            .eq("user_id", user_id)
            .eq("id", conversation_id)
            .execute()
        )
        used_event_ids.add(match.event_id)
        linked_count += 1

    return linked_count


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
    summary="Today's briefing: upcoming meetings and open commitments",
)
async def get_today(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> TodayBriefing:
    """Return dashboard context: upcoming meetings, commitments, activity, and connections."""
    user_id: str = current_user["sub"]
    raw_jwt: str = current_user["_raw_jwt"]
    db = get_client(raw_jwt)
    _, refresh_token = _get_google_tokens(db, user_id)

    try:
        refreshed_access_token = await refresh_access_token(refresh_token)
    except Exception as exc:
        logger.error("Google token refresh failed for user=%s: %s", user_id, type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to refresh Google access. Please sign in again.",
        ) from exc

    (
        db.table("user_index")
        .update({"google_access_token": refreshed_access_token})
        .eq("user_id", user_id)
        .execute()
    )

    today_start = datetime.combine(date.today(), time.min, tzinfo=UTC)
    today_end = today_start + timedelta(days=1)
    now = datetime.now(tz=UTC)

    try:
        today_events = await list_calendar_events(
            refreshed_access_token,
            time_min=today_start,
            time_max=today_end,
        )
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google Calendar access denied. Please sign in again.",
        ) from exc
    except Exception as exc:
        logger.error("Calendar read failed for user=%s: %s", user_id, type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to retrieve meetings from Google Calendar.",
        ) from exc

    sync_start = now - timedelta(days=_CALENDAR_LINK_LOOKBACK_DAYS)
    sync_end = now + timedelta(days=_CALENDAR_LINK_LOOKAHEAD_DAYS)
    unlinked_result = (
        db.table("conversations")
        .select("id, meeting_date, calendar_event_id")
        .eq("user_id", user_id)
        .is_("calendar_event_id", "null")
        .gte("meeting_date", sync_start.isoformat())
        .lte("meeting_date", sync_end.isoformat())
        .execute()
    )
    conversations_needing_links = unlinked_result.data or []

    linked_count = 0
    if conversations_needing_links:
        conversation_times = [
            parsed
            for row in conversations_needing_links
            if (parsed := _parse_datetime(row.get("meeting_date"))) is not None
        ]
        if conversation_times:
            link_window_start = min(conversation_times) - timedelta(hours=12)
            link_window_end = max(conversation_times) + timedelta(hours=12)

            try:
                sync_events = await list_calendar_events(
                    refreshed_access_token,
                    time_min=link_window_start,
                    time_max=link_window_end,
                )
            except Exception as exc:
                logger.warning(
                    "Conversation/calendar linking skipped for user=%s due to fetch error: %s",
                    user_id,
                    type(exc).__name__,
                )
            else:
                linked_count = _sync_conversation_calendar_links(
                    db,
                    user_id,
                    conversations_needing_links,
                    sync_events,
                )
                if linked_count:
                    logger.info(
                        "Calendar linking updated %d conversation rows for user=%s",
                        linked_count,
                        user_id,
                    )

    # Trigger user-scoped recurring-brief scheduling asynchronously.
    # Failures here should not block the read endpoint.
    try:
        schedule_recurring_briefs.delay(
            user_id=user_id,
            user_jwt=raw_jwt,
            google_refresh_token=refresh_token,
        )
    except Exception as exc:
        logger.warning(
            "Recurring brief scheduler dispatch failed for user=%s: %s",
            user_id,
            type(exc).__name__,
        )

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
    recent_connections = _load_recent_connections(db, user_id)

    return TodayBriefing(
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
        recent_connections=recent_connections,
    )
