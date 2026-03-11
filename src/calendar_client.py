"""
Google Calendar client for Farz calendar sync and today briefing.

This module fetches events from the authenticated user's primary calendar.
It returns structured event metadata used for:
- /calendar/today upcoming meeting cards
- conversation ↔ calendar_event_id matching
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

import httpx
from pydantic import BaseModel

_CALENDAR_EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"


class CalendarEvent(BaseModel):
    event_id: str
    title: str
    start_time: datetime
    end_time: datetime | None = None
    attendees: list[str]
    recurring_event_id: str | None = None
    is_recurring: bool = False


def _to_rfc3339_utc(value: datetime) -> str:
    aware_value = value if value.tzinfo else value.replace(tzinfo=UTC)
    return aware_value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_event_time(raw: dict[str, Any]) -> datetime | None:
    date_time_value = raw.get("dateTime")
    if isinstance(date_time_value, str) and date_time_value.strip():
        parsed = datetime.fromisoformat(date_time_value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)

    date_value = raw.get("date")
    if isinstance(date_value, str) and date_value.strip():
        parsed_date = date.fromisoformat(date_value)
        return datetime(
            year=parsed_date.year,
            month=parsed_date.month,
            day=parsed_date.day,
            tzinfo=UTC,
        )

    return None


def _extract_attendees(raw_attendees: Any) -> list[str]:
    if not isinstance(raw_attendees, list):
        return []

    normalized: list[str] = []
    seen: set[str] = set()
    for item in raw_attendees:
        if not isinstance(item, dict):
            continue

        display_name = item.get("displayName")
        email = item.get("email")
        display_name_text = display_name.strip() if isinstance(display_name, str) else ""
        email_text = email.strip() if isinstance(email, str) else ""

        if display_name_text and email_text:
            attendee = (
                f"{display_name_text} <{email_text}>"
                if display_name_text.lower() != email_text.lower()
                else display_name_text
            )
        elif display_name_text:
            attendee = display_name_text
        elif email_text:
            attendee = email_text
        else:
            continue

        if attendee in seen:
            continue
        seen.add(attendee)
        normalized.append(attendee)

    return normalized


async def list_calendar_events(
    access_token: str,
    time_min: datetime,
    time_max: datetime,
    *,
    max_results: int = 250,
) -> list[CalendarEvent]:
    """Return calendar events for the user's primary calendar in [time_min, time_max].

    Args:
        access_token: Google OAuth access token with calendar.readonly scope.
        time_min: Inclusive lower bound (timezone-aware preferred).
        time_max: Exclusive upper bound (timezone-aware preferred).
        max_results: Page size for each Calendar API request.

    Raises:
        PermissionError: If access token is invalid / expired.
        httpx.HTTPStatusError: On non-401 API failures.
    """
    events: list[CalendarEvent] = []
    page_token: str | None = None

    async with httpx.AsyncClient(timeout=20.0) as client:
        while True:
            params: dict[str, str] = {
                "singleEvents": "true",
                "orderBy": "startTime",
                "timeMin": _to_rfc3339_utc(time_min),
                "timeMax": _to_rfc3339_utc(time_max),
                "maxResults": str(max_results),
            }
            if page_token:
                params["pageToken"] = page_token

            response = await client.get(
                _CALENDAR_EVENTS_URL,
                params=params,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            payload, page_token = _decode_calendar_response(response)
            events.extend(_parse_calendar_items(payload))
            if not page_token:
                break

    events.sort(key=lambda event: event.start_time)
    return events


def list_calendar_events_sync(
    access_token: str,
    time_min: datetime,
    time_max: datetime,
    *,
    max_results: int = 250,
) -> list[CalendarEvent]:
    """Sync variant of list_calendar_events for Celery worker tasks."""
    events: list[CalendarEvent] = []
    page_token: str | None = None

    with httpx.Client(timeout=20.0) as client:
        while True:
            params: dict[str, str] = {
                "singleEvents": "true",
                "orderBy": "startTime",
                "timeMin": _to_rfc3339_utc(time_min),
                "timeMax": _to_rfc3339_utc(time_max),
                "maxResults": str(max_results),
            }
            if page_token:
                params["pageToken"] = page_token

            response = client.get(
                _CALENDAR_EVENTS_URL,
                params=params,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            payload, page_token = _decode_calendar_response(response)
            events.extend(_parse_calendar_items(payload))
            if not page_token:
                break

    events.sort(key=lambda event: event.start_time)
    return events


def _decode_calendar_response(response: httpx.Response) -> tuple[dict[str, Any], str | None]:
    if response.status_code == 401:
        raise PermissionError("Google Calendar access token is invalid or expired")
    response.raise_for_status()
    payload = response.json()
    next_page_token = payload.get("nextPageToken")
    page_token = next_page_token if isinstance(next_page_token, str) else None
    return payload, page_token


def _parse_calendar_items(payload: dict[str, Any]) -> list[CalendarEvent]:
    parsed: list[CalendarEvent] = []
    raw_items = payload.get("items")
    if not isinstance(raw_items, list):
        return parsed

    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            continue
        if raw_item.get("status") == "cancelled":
            continue

        event_id = raw_item.get("id")
        if not isinstance(event_id, str) or not event_id.strip():
            continue

        start_payload = raw_item.get("start")
        end_payload = raw_item.get("end")
        if isinstance(start_payload, dict):
            start_time = _parse_event_time(start_payload)
        else:
            start_time = None

        if isinstance(end_payload, dict):
            end_time = _parse_event_time(end_payload)
        else:
            end_time = None
        if start_time is None:
            continue

        summary = raw_item.get("summary")
        if isinstance(summary, str) and summary.strip():
            title = summary.strip()
        else:
            title = "Untitled meeting"

        recurring_event_id = raw_item.get("recurringEventId")
        recurring_event = (
            recurring_event_id
            if isinstance(recurring_event_id, str) and recurring_event_id.strip()
            else None
        )
        recurrence = raw_item.get("recurrence")
        is_recurring = recurring_event is not None or (
            isinstance(recurrence, list) and bool(recurrence)
        )

        parsed.append(
            CalendarEvent(
                event_id=event_id,
                title=title,
                start_time=start_time,
                end_time=end_time,
                attendees=_extract_attendees(raw_item.get("attendees")),
                recurring_event_id=recurring_event,
                is_recurring=is_recurring,
            )
        )

    return parsed
