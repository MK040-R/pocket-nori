"""
Home route — personalized daily summary.

GET /home/summary — AI-generated 2-3 sentence briefing for the user's day,
drawing on upcoming calendar meetings, open action count, and recent topic activity.
Cached per user per day for up to 6 hours.
"""

import logging
from datetime import UTC, date, datetime, time
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.api.deps import get_current_user
from src.cache_utils import build_user_cache_key, get_cached_json, set_cached_json
from src.database import get_client
from src.llm_client import generate_home_summary

logger = logging.getLogger(__name__)

router = APIRouter()

_HOME_SUMMARY_CACHE_TTL_SECONDS = 6 * 60 * 60  # 6 hours


class HomeSummary(BaseModel):
    summary: str
    generated_at: str


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


@router.get(
    "/summary",
    response_model=HomeSummary,
    summary="AI-generated daily briefing for the home page",
)
async def get_home_summary(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> HomeSummary:
    """Return a 2-3 sentence personalized daily briefing.

    Draws on upcoming calendar meetings (best-effort), open commitment count,
    and recent topic activity. Cached per user for up to 6 hours.
    """
    user_id: str = current_user["sub"]
    raw_jwt: str = current_user["_raw_jwt"]
    db = get_client(raw_jwt)

    cache_key = build_user_cache_key(
        user_id,
        "home_summary",
        {"date": date.today().isoformat()},
    )
    cached = get_cached_json(cache_key)
    if cached is not None:
        return HomeSummary.model_validate(cached)

    # --- Open commitment count ---
    commitment_rows = (
        db.table("commitments")
        .select("id")
        .eq("user_id", user_id)
        .eq("status", "open")
        .limit(200)
        .execute()
    )
    open_commitment_count = len(commitment_rows.data or [])

    # --- Recent topic labels (up to 3 distinct) ---
    topic_rows = (
        db.table("topics")
        .select("label")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(15)
        .execute()
    )
    seen: set[str] = set()
    recent_topic_labels: list[str] = []
    for row in topic_rows.data or []:
        lbl = str(row.get("label", "") or "").strip()
        if lbl and lbl not in seen:
            seen.add(lbl)
            recent_topic_labels.append(lbl)
        if len(recent_topic_labels) >= 3:
            break

    # --- Upcoming meetings via Google Calendar (best-effort) ---
    upcoming_meeting_titles: list[str] = []
    try:
        token_rows = (
            db.table("user_index")
            .select("google_access_token, google_refresh_token")
            .eq("user_id", user_id)
            .execute()
        )
        if token_rows.data:
            token_row = token_rows.data[0]
            access_token = str(token_row.get("google_access_token") or "").strip()
            refresh_token = str(token_row.get("google_refresh_token") or "").strip()

            if refresh_token:
                from src.calendar_client import list_calendar_events
                from src.drive_client import refresh_access_token

                now = datetime.now(tz=UTC)
                today_end = datetime.combine(date.today(), time.max, tzinfo=UTC)

                if access_token:
                    try:
                        events = await list_calendar_events(
                            access_token, time_min=now, time_max=today_end
                        )
                    except PermissionError:
                        refreshed = await refresh_access_token(refresh_token)
                        events = await list_calendar_events(
                            refreshed, time_min=now, time_max=today_end
                        )
                else:
                    refreshed = await refresh_access_token(refresh_token)
                    events = await list_calendar_events(refreshed, time_min=now, time_max=today_end)

                upcoming_meeting_titles = [
                    event.title for event in events if event.start_time >= now
                ][:3]
    except Exception as exc:
        logger.info(
            "Home summary — calendar fetch skipped for user=%s (%s)",
            user_id,
            type(exc).__name__,
        )

    # --- Generate summary ---
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
