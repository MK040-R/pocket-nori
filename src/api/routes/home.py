"""
Home routes — dashboard payload and personalized daily summary.

GET /home/dashboard — single payload for the Home screen.
GET /home/summary   — AI-generated 2-3 sentence briefing for the user's day.
"""

import logging
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.api.deps import get_current_user
from src.api.routes.briefs import UpcomingBrief
from src.api.routes.calendar import (
    UpcomingMeeting,
    _get_google_tokens,
    _load_calendar_events_with_refresh,
)
from src.api.routes.index_stats import IndexStats, load_index_stats_snapshot
from src.cache_utils import build_user_cache_key, get_cached_json, set_cached_json
from src.database import get_client
from src.llm_client import generate_home_summary

logger = logging.getLogger(__name__)

router = APIRouter()

_HOME_DASHBOARD_CACHE_TTL_SECONDS = 60
_HOME_SUMMARY_CACHE_TTL_SECONDS = 6 * 60 * 60
_HOME_ACTION_LIMIT = 3


class HomeSummary(BaseModel):
    summary: str
    generated_at: str


class HomeActionItem(BaseModel):
    id: str
    text: str
    owner: str
    due_date: str | None
    conversation_title: str


class HomeActions(BaseModel):
    commitment: list[HomeActionItem]
    follow_up: list[HomeActionItem]


class HomeToday(BaseModel):
    upcoming_meetings: list[UpcomingMeeting]


class HomeDashboard(BaseModel):
    today: HomeToday
    stats: IndexStats
    summary: HomeSummary
    prep_push: UpcomingBrief | None
    actions: HomeActions


def _plain_fallback(upcoming: list[str], commitment_count: int) -> str:
    """Plain-text fallback used when the LLM call fails."""
    parts: list[str] = []
    if upcoming:
        noun = "meeting" if len(upcoming) == 1 else "meetings"
        parts.append(f"You have {len(upcoming)} upcoming {noun} today.")
    else:
        parts.append("Your schedule is clear for the rest of today.")
    if commitment_count:
        noun = "action" if commitment_count == 1 else "actions"
        parts.append(f"You have {commitment_count} open {noun} to work through.")
    else:
        parts.append("No open actions — you're all caught up.")
    return " ".join(parts)


def _load_recent_topic_labels(db: Any, user_id: str, limit: int = 3) -> list[str]:
    topic_rows = (
        db.table("topics")
        .select("label")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(max(limit * 5, 10))
        .execute()
    )
    seen: set[str] = set()
    labels: list[str] = []
    for row in topic_rows.data or []:
        label = str(row.get("label", "") or "").strip()
        if not label or label in seen:
            continue
        seen.add(label)
        labels.append(label)
        if len(labels) >= limit:
            break
    return labels


def _load_open_action_rows(
    db: Any,
    user_id: str,
    action_type: str,
    *,
    limit: int = _HOME_ACTION_LIMIT,
) -> list[dict[str, Any]]:
    rows = (
        db.table("commitments")
        .select("id, text, owner, due_date, conversation_id")
        .eq("user_id", user_id)
        .eq("status", "open")
        .eq("action_type", action_type)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return rows.data or []


def _count_open_actions(db: Any, user_id: str) -> int:
    result = (
        db.table("commitments")
        .select("id", count="exact")
        .eq("user_id", user_id)
        .eq("status", "open")
        .limit(1)
        .execute()
    )
    exact_count = getattr(result, "count", None)
    if isinstance(exact_count, int):
        return exact_count
    return len(result.data or [])


def _build_home_actions(
    db: Any,
    user_id: str,
    *,
    limit: int = _HOME_ACTION_LIMIT,
) -> HomeActions:
    commitment_rows = _load_open_action_rows(db, user_id, "commitment", limit=limit)
    follow_up_rows = _load_open_action_rows(db, user_id, "follow_up", limit=limit)
    all_rows = commitment_rows + follow_up_rows

    conversation_ids = sorted(
        {str(row.get("conversation_id") or "") for row in all_rows if row.get("conversation_id")}
    )
    conversation_titles: dict[str, str] = {}
    if conversation_ids:
        conversation_rows = (
            db.table("conversations")
            .select("id, title")
            .eq("user_id", user_id)
            .in_("id", conversation_ids)
            .execute()
        ).data or []
        conversation_titles = {
            str(row["id"]): str(row.get("title") or "")
            for row in conversation_rows
            if row.get("id")
        }

    def _serialize(rows: list[dict[str, Any]]) -> list[HomeActionItem]:
        return [
            HomeActionItem(
                id=str(row.get("id") or ""),
                text=str(row.get("text") or ""),
                owner=str(row.get("owner") or ""),
                due_date=(str(row.get("due_date")) if row.get("due_date") is not None else None),
                conversation_title=conversation_titles.get(
                    str(row.get("conversation_id") or ""),
                    "",
                ),
            )
            for row in rows
            if row.get("id")
        ]

    return HomeActions(
        commitment=_serialize(commitment_rows),
        follow_up=_serialize(follow_up_rows),
    )


async def _load_dashboard_calendar_events(
    db: Any,
    user_id: str,
    *,
    time_min: datetime,
    time_max: datetime,
) -> list[Any]:
    try:
        access_token, refresh_token = _get_google_tokens(db, user_id)
    except HTTPException as exc:
        logger.info(
            "Home dashboard — calendar unavailable for user=%s (%s)",
            user_id,
            exc.detail,
        )
        return []

    try:
        _, events = await _load_calendar_events_with_refresh(
            db,
            user_id,
            access_token,
            refresh_token,
            time_min=time_min,
            time_max=time_max,
        )
        return events
    except Exception as exc:
        logger.info(
            "Home dashboard — calendar fetch skipped for user=%s (%s)",
            user_id,
            type(exc).__name__,
        )
        return []


def _preview_text(content: str, limit: int = 220) -> str:
    preview = content[:limit].strip()
    if len(content) > limit:
        return f"{preview}..."
    return preview


def _resolve_prep_push(
    db: Any,
    user_id: str,
    events: list[Any],
    *,
    now: datetime,
    open_commitments_count: int,
    related_topic_count: int,
) -> UpcomingBrief | None:
    candidate_events = []
    for event in events:
        event_id = str(getattr(event, "event_id", "") or "")
        if not event_id:
            continue
        event_start = getattr(event, "start_time", now)
        minutes_until_start = max(0, int((event_start - now).total_seconds() / 60))
        if minutes_until_start <= 120:
            candidate_events.append((event, minutes_until_start))
    if not candidate_events:
        return None

    event_ids = [str(getattr(event, "event_id", "")) for event, _ in candidate_events]
    brief_rows = (
        db.table("briefs")
        .select("id, conversation_id, calendar_event_id, content, generated_at")
        .eq("user_id", user_id)
        .in_("calendar_event_id", event_ids)
        .order("generated_at", desc=True)
        .execute()
    ).data or []
    latest_brief_by_event: dict[str, dict[str, Any]] = {}
    for row in brief_rows:
        event_id = str(row.get("calendar_event_id") or "")
        if event_id and event_id not in latest_brief_by_event:
            latest_brief_by_event[event_id] = row

    for event, minutes_until_start in sorted(candidate_events, key=lambda item: item[1]):
        if minutes_until_start > 60:
            continue
        event_id = str(getattr(event, "event_id", "") or "")
        brief_row = latest_brief_by_event.get(event_id)
        if brief_row is None:
            continue
        conversation_id_value = brief_row.get("conversation_id")
        return UpcomingBrief(
            brief_id=str(brief_row.get("id") or ""),
            conversation_id=(
                str(conversation_id_value) if conversation_id_value is not None else None
            ),
            calendar_event_id=event_id,
            event_title=str(getattr(event, "title", "") or ""),
            event_start=getattr(event, "start_time", now).isoformat(),
            minutes_until_start=minutes_until_start,
            preview=_preview_text(str(brief_row.get("content") or "")),
            open_commitments_count=open_commitments_count,
            related_topic_count=related_topic_count,
        )
    return None


def _build_summary_payload(
    user_id: str,
    *,
    upcoming_meeting_titles: list[str],
    open_commitment_count: int,
    recent_topic_labels: list[str],
) -> HomeSummary:
    cache_key = build_user_cache_key(
        user_id,
        "home_summary",
        {"date": date.today().isoformat()},
    )
    cached = get_cached_json(cache_key)
    if cached is not None:
        return HomeSummary.model_validate(cached)

    try:
        summary_text = generate_home_summary(
            upcoming_meeting_titles=upcoming_meeting_titles,
            open_commitment_count=open_commitment_count,
            recent_topic_labels=recent_topic_labels,
        )
    except Exception as exc:
        logger.warning(
            "Home summary LLM call failed for user=%s: %s",
            user_id,
            type(exc).__name__,
        )
        summary_text = _plain_fallback(upcoming_meeting_titles, open_commitment_count)

    payload = HomeSummary(
        summary=summary_text,
        generated_at=datetime.now(tz=UTC).isoformat(),
    )
    set_cached_json(cache_key, payload.model_dump(mode="json"), _HOME_SUMMARY_CACHE_TTL_SECONDS)
    return payload


@router.get(
    "/dashboard",
    response_model=HomeDashboard,
    summary="Single payload for the Home screen",
)
async def get_home_dashboard(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> HomeDashboard:
    user_id: str = current_user["sub"]
    raw_jwt: str = current_user["_raw_jwt"]
    db = get_client(raw_jwt)
    now = datetime.now(tz=UTC)
    today_start = datetime.combine(date.today(), time.min, tzinfo=UTC)
    today_end = today_start + timedelta(days=2)
    cache_key = build_user_cache_key(
        user_id,
        "home_dashboard",
        {"bucket": now.strftime("%Y-%m-%dT%H:%M")},
    )
    cached = get_cached_json(cache_key)
    if cached is not None:
        return HomeDashboard.model_validate(cached)

    stats = load_index_stats_snapshot(db, user_id)
    actions = _build_home_actions(db, user_id)
    open_commitment_count = _count_open_actions(db, user_id)
    recent_topic_labels = _load_recent_topic_labels(db, user_id)
    events = await _load_dashboard_calendar_events(
        db,
        user_id,
        time_min=today_start,
        time_max=today_end,
    )

    upcoming_meetings = [
        UpcomingMeeting(
            id=str(getattr(event, "event_id", "") or ""),
            title=str(getattr(event, "title", "") or ""),
            start_time=getattr(event, "start_time", now).isoformat(),
            attendees=list(getattr(event, "attendees", []) or []),
        )
        for event in events
        if getattr(event, "start_time", now) >= now and getattr(event, "event_id", None)
    ]
    summary = _build_summary_payload(
        user_id,
        upcoming_meeting_titles=[meeting.title for meeting in upcoming_meetings[:3]],
        open_commitment_count=open_commitment_count,
        recent_topic_labels=recent_topic_labels,
    )
    prep_push = _resolve_prep_push(
        db,
        user_id,
        events,
        now=now,
        open_commitments_count=open_commitment_count,
        related_topic_count=stats.topic_count,
    )

    payload = HomeDashboard(
        today=HomeToday(upcoming_meetings=upcoming_meetings),
        stats=stats,
        summary=summary,
        prep_push=prep_push,
        actions=actions,
    )
    set_cached_json(cache_key, payload.model_dump(mode="json"), _HOME_DASHBOARD_CACHE_TTL_SECONDS)
    return payload


@router.get(
    "/summary",
    response_model=HomeSummary,
    summary="AI-generated daily briefing for the home page",
)
async def get_home_summary(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> HomeSummary:
    """Return a 2-3 sentence personalized daily briefing."""
    user_id: str = current_user["sub"]
    raw_jwt: str = current_user["_raw_jwt"]
    db = get_client(raw_jwt)
    now = datetime.now(tz=UTC)
    today_end = datetime.combine(date.today(), time.max, tzinfo=UTC)

    open_commitment_count = _count_open_actions(db, user_id)
    recent_topic_labels = _load_recent_topic_labels(db, user_id)
    events = await _load_dashboard_calendar_events(
        db,
        user_id,
        time_min=now,
        time_max=today_end,
    )
    upcoming_meeting_titles = [
        str(getattr(event, "title", "") or "")
        for event in events
        if getattr(event, "start_time", now) >= now and getattr(event, "title", None)
    ][:3]

    return _build_summary_payload(
        user_id,
        upcoming_meeting_titles=upcoming_meeting_titles,
        open_commitment_count=open_commitment_count,
        recent_topic_labels=recent_topic_labels,
    )
