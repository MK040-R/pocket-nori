"""
Supabase client singleton.

Usage:
    from src.database import get_client, get_admin_client

- get_client(jwt)       — returns a client authenticated as the calling user (respects RLS).
- get_admin_client()    — returns a service-role client that BYPASSES RLS.
                          Use ONLY in migration scripts and admin-only tooling.
                          NEVER call this from API route handlers or Celery workers.
"""

import logging

from supabase import Client, create_client

from src.config import settings

logger = logging.getLogger(__name__)


def get_client(user_jwt: str) -> Client:
    """Return a Supabase client scoped to the authenticated user.

    The client uses the user's JWT so all queries are subject to RLS policies.
    Each call creates a new client instance to avoid session bleed between requests.

    Args:
        user_jwt: The bearer token issued to the user by Supabase Auth.

    Returns:
        An authenticated Supabase Client.
    """
    client = create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)
    client.auth.set_session(user_jwt, "")
    return client


def get_admin_client() -> Client:
    """Return a Supabase client using the service role key.

    WARNING: This client BYPASSES Row Level Security entirely.
    Permitted uses:
    - Database migration scripts
    - CI test harness setup/teardown
    - Scheduled maintenance jobs run outside the request lifecycle

    FORBIDDEN uses:
    - FastAPI route handlers
    - Celery worker task bodies
    - Any code path reachable by user input

    Returns:
        A service-role Supabase Client.
    """
    logger.warning(
        "Admin (service-role) Supabase client created — RLS is bypassed. "
        "Ensure this is only called from migration or admin scripts."
    )
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)
