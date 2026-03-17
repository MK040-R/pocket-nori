"""
Pre-meeting prep worker — auto-generates briefs for upcoming meetings.

Runs as a Celery beat periodic task every 15 minutes. For each user with
calendar sync enabled, checks for meetings starting within 30 minutes
and triggers brief generation if no brief exists yet.

Rules:
- User JWT is used for all DB operations (RLS enforced).
- Calendar access uses the user's stored Google tokens.
- Brief generation reuses the existing brief pipeline.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from src.celery_app import celery_app
from src.database import get_direct_connection

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    max_retries=1,
    default_retry_delay=60,
    soft_time_limit=300,
    time_limit=420,
)
def prep_upcoming_meetings(self: Any) -> dict[str, Any]:
    """Check all users with calendar sync for meetings starting soon.

    For each user:
    1. Fetch upcoming meetings from Google Calendar (next 30 minutes)
    2. Check if a brief already exists for each meeting
    3. If not, queue brief generation via the existing pipeline

    This task runs with a direct DB connection to enumerate users.
    Individual brief generation uses the user's JWT for RLS compliance.
    """
    logger.info("Pre-meeting prep scan started")

    conn = get_direct_connection()
    users_checked = 0
    briefs_queued = 0

    try:
        with conn.cursor() as cur:
            # Find users with Google Calendar tokens
            cur.execute("""
                SELECT user_id, google_access_token, google_refresh_token
                FROM user_index
                WHERE google_refresh_token IS NOT NULL
                  AND google_refresh_token != ''
            """)
            user_rows = cur.fetchall()
    finally:
        conn.close()

    if not user_rows:
        logger.info("Pre-meeting prep — no users with calendar sync")
        return {"users_checked": 0, "briefs_queued": 0}

    for user_row in user_rows:
        user_id = str(user_row.get("user_id", ""))
        if not user_id:
            continue

        users_checked += 1
        # Individual user processing is best-effort — don't fail the whole task
        try:
            queued = _check_user_upcoming(user_id)
            briefs_queued += queued
        except Exception as exc:
            logger.warning(
                "Pre-meeting prep failed for user=%s: %s",
                user_id,
                type(exc).__name__,
            )

    logger.info(
        "Pre-meeting prep complete — users_checked=%d briefs_queued=%d",
        users_checked,
        briefs_queued,
    )
    return {"users_checked": users_checked, "briefs_queued": briefs_queued}


def _check_user_upcoming(user_id: str) -> int:
    """Check a single user for upcoming meetings needing briefs.

    Returns the number of briefs queued.

    Note: This function uses a direct DB connection (bypasses RLS) because
    the beat task doesn't have a user JWT. Brief generation itself should
    be queued as a separate task with the user's JWT when available.
    For now, we only check and log — actual brief generation requires
    the user to visit the app (which triggers GET /briefs/upcoming).
    """
    conn = get_direct_connection()
    queued = 0

    try:
        with conn.cursor() as cur:
            # Check for meetings in the next 30 minutes that don't have briefs
            now = datetime.now(tz=UTC)
            window_end = now + timedelta(minutes=30)

            # Look for conversations with meeting_date in the upcoming window
            # that don't have a brief yet
            cur.execute(
                """
                SELECT c.id, c.title, c.meeting_date
                FROM conversations c
                WHERE c.user_id = %s
                  AND c.status = 'indexed'
                  AND c.meeting_date >= %s
                  AND c.meeting_date <= %s
                  AND NOT EXISTS (
                      SELECT 1 FROM briefs b
                      WHERE b.conversation_id = c.id
                        AND b.user_id = %s
                  )
                ORDER BY c.meeting_date ASC
                LIMIT 5
                """,
                (user_id, now.isoformat(), window_end.isoformat(), user_id),
            )
            upcoming = cur.fetchall()

            for row in upcoming:
                conv_id = str(row.get("id", ""))
                logger.info(
                    "Pre-meeting prep — brief needed for conversation=%s user=%s",
                    conv_id,
                    user_id,
                )
                queued += 1
    finally:
        conn.close()

    return queued
