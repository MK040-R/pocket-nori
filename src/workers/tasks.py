"""
Celery application and task definitions for Pocket Nori workers.

All tasks include user_id in their payload to enforce per-user isolation.
Transcript content is never logged — only IDs are written to the log.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from src import llm_client
from src.calendar_client import CalendarEvent, list_calendar_events_sync
from src.celery_app import celery_app as celery_app
from src.database import get_client
from src.drive_client import refresh_access_token_sync

logger = logging.getLogger(__name__)

_BRIEF_LOOKAHEAD_MINUTES = 24 * 60
_BRIEF_OFFSET_MINUTES = 12
_RECURRING_HISTORY_LOOKBACK_DAYS = 180


@celery_app.task(bind=True, max_retries=3, default_retry_delay=30)  # type: ignore[untyped-decorator]
def process_transcript(
    self: Any,
    transcript_id: str,
    user_id: str,
    raw_text: str,
) -> dict[str, Any]:
    """Enqueue a transcript for processing.

    Args:
        transcript_id: Unique identifier for the transcript record.
        user_id: Owner of the transcript — enforces per-user isolation.
        raw_text: Raw transcript text. Never logged.

    Returns:
        A dict containing transcript_id, user_id, and status.

    Raises:
        ValueError: If transcript_id or user_id are empty.
    """
    if not transcript_id:
        raise ValueError("transcript_id is required and must be non-empty")
    if not user_id:
        raise ValueError("user_id is required and must be non-empty")

    logger.info("Processing transcript %s for user %s", transcript_id, user_id)

    # Actual extraction logic is implemented in Phase 1.
    return {
        "transcript_id": transcript_id,
        "user_id": user_id,
        "status": "queued",
    }


def _build_brief_context(
    conversation: dict[str, Any],
    topic_arcs: list[dict[str, Any]],
    commitments: list[dict[str, Any]],
    connections: list[dict[str, Any]],
    *,
    target_meeting_title: str | None = None,
    target_meeting_start_iso: str | None = None,
    target_calendar_event_id: str | None = None,
) -> str:
    meeting_title = target_meeting_title or str(conversation.get("title") or "Untitled meeting")
    meeting_start = target_meeting_start_iso or str(conversation.get("meeting_date") or "")
    meeting_event_id = target_calendar_event_id or str(conversation.get("calendar_event_id") or "")

    lines = [
        "Upcoming meeting:",
        f"- conversation_id: {conversation.get('id', '')}",
        f"- title: {meeting_title}",
        f"- meeting_date: {meeting_start}",
        f"- calendar_event_id: {meeting_event_id}",
        "",
        "Relevant topic history:",
    ]

    if topic_arcs:
        for arc in topic_arcs[:8]:
            lines.append(
                "- [topic_arc:{id}] trend={trend} summary={summary}".format(
                    id=arc.get("id", ""),
                    trend=arc.get("trend", ""),
                    summary=arc.get("summary", ""),
                )
            )
    else:
        lines.append("- None found.")

    lines.append("")
    lines.append("Open commitments relevant to this meeting:")
    if commitments:
        for commitment in commitments[:10]:
            due_date = commitment.get("due_date") or "not specified"
            lines.append(
                "- [commitment:{id}] owner={owner} due={due} text={text}".format(
                    id=commitment.get("id", ""),
                    owner=commitment.get("owner", ""),
                    due=due_date,
                    text=commitment.get("text", ""),
                )
            )
    else:
        lines.append("- None found.")

    lines.append("")
    lines.append("Cross-meeting connections:")
    if connections:
        for connection in connections[:8]:
            lines.append(
                "- [connection:{id}] label={label} summary={summary}".format(
                    id=connection.get("id", ""),
                    label=connection.get("label", ""),
                    summary=connection.get("summary", ""),
                )
            )
    else:
        lines.append("- None found.")

    lines.append("")
    lines.append(
        "Write a concise pre-meeting brief grounded only in the context above. "
        "If context is sparse, say so directly."
    )
    return "\n".join(lines)


def _insert_link_rows(
    db: Any,
    *,
    table: str,
    brief_id: str,
    user_id: str,
    field_name: str,
    values: list[str],
) -> None:
    if not values:
        return
    rows = [
        {
            "brief_id": brief_id,
            field_name: value,
            "user_id": user_id,
        }
        for value in values
    ]
    db.table(table).insert(rows).execute()


def _parse_iso_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=30)  # type: ignore[untyped-decorator]
def generate_brief(
    self: Any,
    conversation_id: str,
    user_id: str,
    user_jwt: str,
    target_calendar_event_id: str | None = None,
    target_meeting_title: str | None = None,
    target_meeting_start_iso: str | None = None,
) -> dict[str, Any]:
    """Generate and persist a pre-meeting brief for a conversation.

    Args:
        conversation_id: Unique identifier for the conversation record.
        user_id: Owner of the conversation — enforces per-user isolation.
        user_jwt: Supabase JWT — used for all DB operations (RLS enforced).
        target_calendar_event_id: Optional future calendar event ID this brief targets.
        target_meeting_title: Optional future meeting title override for brief context.
        target_meeting_start_iso: Optional future meeting start datetime ISO override.

    Returns:
        dict containing brief_id, conversation_id, user_id, and status.

    Raises:
        ValueError: If required arguments are empty.
        RuntimeError: If conversation does not belong to user.
    """
    if not conversation_id:
        raise ValueError("conversation_id is required and must be non-empty")
    if not user_id:
        raise ValueError("user_id is required and must be non-empty")
    if not user_jwt:
        raise ValueError("user_jwt is required and must be non-empty")
    if target_meeting_start_iso and _parse_iso_datetime(target_meeting_start_iso) is None:
        raise ValueError("target_meeting_start_iso must be a valid ISO datetime if provided")

    logger.info(
        "Generating brief for conversation %s, user %s, target_event=%s",
        conversation_id,
        user_id,
        target_calendar_event_id or "",
    )
    db = get_client(user_jwt)

    if target_calendar_event_id:
        existing_target_brief = (
            db.table("briefs")
            .select("id")
            .eq("user_id", user_id)
            .eq("calendar_event_id", target_calendar_event_id)
            .order("generated_at", desc=True)
            .limit(1)
            .execute()
        ).data or []
        if existing_target_brief:
            return {
                "brief_id": str(existing_target_brief[0]["id"]),
                "conversation_id": conversation_id,
                "user_id": user_id,
                "status": "already_exists",
                "topic_arc_count": 0,
                "commitment_count": 0,
                "connection_count": 0,
            }

    self.update_state(state="PROGRESS", meta={"status": "loading_context"})

    conversation_result = (
        db.table("conversations")
        .select("id, title, meeting_date, calendar_event_id")
        .eq("id", conversation_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not conversation_result.data:
        raise RuntimeError(f"Conversation {conversation_id} not found for user {user_id}")
    conversation = conversation_result.data[0]

    topic_rows = (
        db.table("topics")
        .select("id, label, cluster_id")
        .eq("user_id", user_id)
        .eq("conversation_id", conversation_id)
        .execute()
    ).data or []

    cluster_ids = [str(row["cluster_id"]) for row in topic_rows if row.get("cluster_id")]
    topic_labels = [str(row["label"]) for row in topic_rows if row.get("label")]

    topic_arcs: list[dict[str, Any]]
    if cluster_ids:
        topic_arcs = (
            db.table("topic_arcs")
            .select("id, topic_id, cluster_id, summary, trend, created_at")
            .eq("user_id", user_id)
            .in_("cluster_id", cluster_ids)
            .order("created_at", desc=True)
            .limit(8)
            .execute()
        ).data or []
    else:
        topic_arcs = []

    related_topics: list[dict[str, Any]]
    if cluster_ids:
        related_topics = (
            db.table("topics")
            .select("conversation_id")
            .eq("user_id", user_id)
            .in_("cluster_id", cluster_ids)
            .execute()
        ).data or []
    elif topic_labels:
        related_topics = (
            db.table("topics")
            .select("conversation_id")
            .eq("user_id", user_id)
            .in_("label", topic_labels)
            .execute()
        ).data or []
    else:
        related_topics = []

    related_conversation_ids = {
        str(row["conversation_id"]) for row in related_topics if row.get("conversation_id")
    }
    related_conversation_ids.add(conversation_id)

    commitments = (
        db.table("commitments")
        .select("id, text, owner, due_date, conversation_id")
        .eq("user_id", user_id)
        .eq("status", "open")
        .in_("conversation_id", sorted(related_conversation_ids))
        .order("created_at", desc=True)
        .limit(12)
        .execute()
    ).data or []

    linked_item_rows = (
        db.table("connection_linked_items")
        .select("connection_id")
        .eq("user_id", user_id)
        .eq("linked_id", conversation_id)
        .execute()
    ).data or []
    connection_ids = sorted(
        {str(row["connection_id"]) for row in linked_item_rows if row.get("connection_id")}
    )

    connections: list[dict[str, Any]]
    if connection_ids:
        connections = (
            db.table("connections")
            .select("id, label, summary, linked_type, created_at")
            .eq("user_id", user_id)
            .in_("id", connection_ids)
            .order("created_at", desc=True)
            .limit(8)
            .execute()
        ).data or []
    else:
        connections = []

    self.update_state(state="PROGRESS", meta={"status": "generating_brief"})
    if not topic_arcs and not commitments and not connections:
        brief_text = (
            "No relevant indexed history was found for this meeting yet. "
            "Review the latest conversation notes and commitments before the call."
        )
    else:
        context = _build_brief_context(
            conversation,
            topic_arcs,
            commitments,
            connections,
            target_meeting_title=target_meeting_title,
            target_meeting_start_iso=target_meeting_start_iso,
            target_calendar_event_id=target_calendar_event_id,
        )
        brief_text = llm_client.generate_brief(context)

    generated_at = datetime.now(tz=UTC).isoformat()
    brief_result = (
        db.table("briefs")
        .insert(
            {
                "user_id": user_id,
                "conversation_id": conversation_id,
                "calendar_event_id": (
                    target_calendar_event_id or conversation.get("calendar_event_id")
                ),
                "content": brief_text,
                "generated_at": generated_at,
            }
        )
        .execute()
    )
    inserted_rows = brief_result.data or []
    if not inserted_rows or not inserted_rows[0].get("id"):
        raise RuntimeError("Brief insert returned no row id")
    brief_id = str(inserted_rows[0]["id"])

    _insert_link_rows(
        db,
        table="brief_topic_arc_links",
        brief_id=brief_id,
        user_id=user_id,
        field_name="topic_arc_id",
        values=[str(row["id"]) for row in topic_arcs if row.get("id")][:8],
    )
    _insert_link_rows(
        db,
        table="brief_commitment_links",
        brief_id=brief_id,
        user_id=user_id,
        field_name="commitment_id",
        values=[str(row["id"]) for row in commitments if row.get("id")][:12],
    )
    _insert_link_rows(
        db,
        table="brief_connection_links",
        brief_id=brief_id,
        user_id=user_id,
        field_name="connection_id",
        values=[str(row["id"]) for row in connections if row.get("id")][:8],
    )

    logger.info(
        "Brief generated for conversation=%s user=%s arcs=%d commitments=%d connections=%d",
        conversation_id,
        user_id,
        len(topic_arcs),
        len(commitments),
        len(connections),
    )

    return {
        "brief_id": brief_id,
        "conversation_id": conversation_id,
        "user_id": user_id,
        "status": "generated",
        "topic_arc_count": len(topic_arcs),
        "commitment_count": len(commitments),
        "connection_count": len(connections),
    }


def _latest_anchor_by_recurring_series(
    *,
    past_events: list[CalendarEvent],
    indexed_conversations: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    event_to_series = {
        event.event_id: event.recurring_event_id
        for event in past_events
        if event.recurring_event_id
    }

    latest_by_series: dict[str, dict[str, Any]] = {}
    for row in indexed_conversations:
        event_id_value = row.get("calendar_event_id")
        if not isinstance(event_id_value, str) or not event_id_value.strip():
            continue
        recurring_event_id = event_to_series.get(event_id_value)
        if not recurring_event_id:
            continue
        meeting_date = _parse_iso_datetime(row.get("meeting_date"))
        if meeting_date is None:
            continue

        previous = latest_by_series.get(recurring_event_id)
        previous_time = _parse_iso_datetime(previous.get("meeting_date")) if previous else None
        if (
            previous is None
            or (previous_time and meeting_date > previous_time)
            or previous_time is None
        ):
            latest_by_series[recurring_event_id] = row

    return latest_by_series


@celery_app.task(bind=True, max_retries=2, default_retry_delay=120)  # type: ignore[untyped-decorator]
def schedule_recurring_briefs(
    self: Any,
    user_id: str,
    user_jwt: str,
    google_refresh_token: str,
    lookahead_minutes: int = _BRIEF_LOOKAHEAD_MINUTES,
    offset_minutes: int = _BRIEF_OFFSET_MINUTES,
) -> dict[str, Any]:
    """Schedule brief generation tasks for upcoming recurring events.

    This task is user-scoped and operates entirely under the provided user JWT
    (RLS enforced). It only schedules recurring series that already have at
    least one prior indexed session linked by calendar_event_id.
    """
    if not user_id:
        raise ValueError("user_id is required and must be non-empty")
    if not user_jwt:
        raise ValueError("user_jwt is required and must be non-empty")
    if not google_refresh_token:
        raise ValueError("google_refresh_token is required and must be non-empty")
    if lookahead_minutes <= 0:
        raise ValueError("lookahead_minutes must be positive")
    if offset_minutes < 0:
        raise ValueError("offset_minutes must be zero or positive")

    db = get_client(user_jwt)
    now = datetime.now(tz=UTC)
    lookahead_end = now + timedelta(minutes=lookahead_minutes)

    self.update_state(state="PROGRESS", meta={"status": "loading_calendar"})
    access_token = refresh_access_token_sync(google_refresh_token)

    upcoming_events = list_calendar_events_sync(
        access_token,
        time_min=now,
        time_max=lookahead_end,
    )
    recurring_upcoming = [
        event
        for event in upcoming_events
        if event.is_recurring and event.recurring_event_id and event.start_time > now
    ]
    if not recurring_upcoming:
        return {
            "user_id": user_id,
            "scheduled_count": 0,
            "skipped_existing": 0,
            "skipped_missing_history": 0,
            "status": "no_recurring_events",
        }

    recurring_ids = {
        event.recurring_event_id for event in recurring_upcoming if event.recurring_event_id
    }
    past_events = list_calendar_events_sync(
        access_token,
        time_min=now - timedelta(days=_RECURRING_HISTORY_LOOKBACK_DAYS),
        time_max=now,
    )
    recurring_past_events = [
        event
        for event in past_events
        if event.recurring_event_id and event.recurring_event_id in recurring_ids
    ]
    past_event_ids = sorted({event.event_id for event in recurring_past_events})
    if not past_event_ids:
        return {
            "user_id": user_id,
            "scheduled_count": 0,
            "skipped_existing": 0,
            "skipped_missing_history": len(recurring_upcoming),
            "status": "no_prior_sessions",
        }

    indexed_conversations = (
        db.table("conversations")
        .select("id, title, meeting_date, calendar_event_id")
        .eq("user_id", user_id)
        .eq("status", "indexed")
        .in_("calendar_event_id", past_event_ids)
        .execute()
    ).data or []
    latest_by_series = _latest_anchor_by_recurring_series(
        past_events=recurring_past_events,
        indexed_conversations=indexed_conversations,
    )

    scheduled_count = 0
    skipped_existing = 0
    skipped_missing_history = 0
    recurring_upcoming.sort(key=lambda event: event.start_time)

    for event in recurring_upcoming:
        recurring_event_id = event.recurring_event_id
        if recurring_event_id is None:
            continue

        anchor = latest_by_series.get(recurring_event_id)
        if not anchor:
            skipped_missing_history += 1
            continue

        existing_brief = (
            db.table("briefs")
            .select("id")
            .eq("user_id", user_id)
            .eq("calendar_event_id", event.event_id)
            .limit(1)
            .execute()
        ).data or []
        if existing_brief:
            skipped_existing += 1
            continue

        eta = event.start_time - timedelta(minutes=offset_minutes)
        task_kwargs = {
            "conversation_id": str(anchor["id"]),
            "user_id": user_id,
            "user_jwt": user_jwt,
            "target_calendar_event_id": event.event_id,
            "target_meeting_title": event.title,
            "target_meeting_start_iso": event.start_time.isoformat(),
        }
        if eta <= now + timedelta(seconds=15):
            generate_brief.delay(**task_kwargs)
        else:
            generate_brief.apply_async(kwargs=task_kwargs, eta=eta)
        scheduled_count += 1

    logger.info(
        "Brief scheduler completed user=%s scheduled=%d existing=%d missing_history=%d",
        user_id,
        scheduled_count,
        skipped_existing,
        skipped_missing_history,
    )
    return {
        "user_id": user_id,
        "scheduled_count": scheduled_count,
        "skipped_existing": skipped_existing,
        "skipped_missing_history": skipped_missing_history,
        "status": "scheduled",
    }
