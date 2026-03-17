"""
test_rls_isolation.py — Pytest test suite validating per-user isolation via
Supabase Row Level Security (RLS).

Prerequisites:
  1. SUPABASE_URL, SUPABASE_SERVICE_KEY, SUPABASE_ANON_KEY set in .env
  2. Migration 001_rls_test_setup.sql applied to the Supabase project
  3. setup_test_users.py has been run (produces test_credentials.json)

Run with:
    pytest test_rls_isolation.py -v
"""

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest
from dotenv import load_dotenv
from supabase import Client, create_client

# ---------------------------------------------------------------------------
# Environment & credential loading
# ---------------------------------------------------------------------------

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")

CREDENTIALS_PATH = Path(__file__).parent / "test_credentials.json"


def _require_env() -> None:
    missing = [
        name
        for name, val in {
            "SUPABASE_URL": SUPABASE_URL,
            "SUPABASE_SERVICE_KEY": SUPABASE_SERVICE_KEY,
            "SUPABASE_ANON_KEY": SUPABASE_ANON_KEY,
        }.items()
        if not val
    ]
    if missing:
        pytest.skip(
            f"Required environment variables not set: {', '.join(missing)}. "
            "Run setup_test_users.py after adding credentials to .env."
        )


def _load_credentials() -> dict:
    if not CREDENTIALS_PATH.exists():
        pytest.skip(
            "test_credentials.json not found. Run setup_test_users.py first."
        )
    with CREDENTIALS_PATH.open() as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def credentials() -> dict:
    _require_env()
    return _load_credentials()


@pytest.fixture(scope="session")
def service_client() -> Client:
    """Supabase client authenticated with the service role key.
    Bypasses RLS — represents server-side admin access."""
    _require_env()
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)


def _user_client(access_token: str, refresh_token: str) -> Client:
    """Return a Supabase client authenticated as a specific user via JWT.

    Both access_token and refresh_token must be non-empty.  supabase-py v2
    raises ValueError if either is an empty string.  setup_test_users.py
    stores the refresh_token from the sign-in session alongside the access
    token, so both are always available from test_credentials.json.
    """
    client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    client.auth.set_session(access_token, refresh_token)
    return client


@pytest.fixture(scope="session")
def user_a_client(credentials: dict) -> Client:
    return _user_client(
        credentials["user_a"]["access_token"],
        credentials["user_a"]["refresh_token"],
    )


@pytest.fixture(scope="session")
def user_b_client(credentials: dict) -> Client:
    return _user_client(
        credentials["user_b"]["access_token"],
        credentials["user_b"]["refresh_token"],
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRLSIsolation:
    """
    Validates that Supabase RLS enforces strict per-user data isolation for the
    `conversations` table.
    """

    def test_user_a_sees_only_own_rows(
        self, user_a_client: Client, credentials: dict
    ) -> None:
        """user_a JWT → query conversations → only user_a rows are returned."""
        user_a_id = credentials["user_a"]["user_id"]

        response = user_a_client.table("conversations").select("*").execute()
        rows = response.data

        assert len(rows) > 0, "user_a should see at least one of their own rows"
        for row in rows:
            assert row["user_id"] == user_a_id, (
                f"user_a received a row belonging to a different user: {row['user_id']}"
            )

    def test_user_b_sees_only_own_rows(
        self, user_b_client: Client, credentials: dict
    ) -> None:
        """user_b JWT → query conversations → only user_b rows are returned."""
        user_b_id = credentials["user_b"]["user_id"]

        response = user_b_client.table("conversations").select("*").execute()
        rows = response.data

        assert len(rows) > 0, "user_b should see at least one of their own rows"
        for row in rows:
            assert row["user_id"] == user_b_id, (
                f"user_b received a row belonging to a different user: {row['user_id']}"
            )

    def test_cross_user_isolation(
        self,
        user_a_client: Client,
        service_client: Client,
        credentials: dict,
    ) -> None:
        """user_a JWT → attempt to fetch a row owned by user_b by ID → empty result.

        RLS silently filters out rows the authenticated user does not own — it does
        not raise an error, it simply returns no rows. This is the expected and
        correct behaviour.
        """
        user_b_id = credentials["user_b"]["user_id"]

        # First, fetch one of user_b's row IDs using the admin client
        admin_response = (
            service_client.table("conversations")
            .select("id")
            .eq("user_id", user_b_id)
            .limit(1)
            .execute()
        )
        assert admin_response.data, "Expected at least one user_b conversation row in DB"
        user_b_row_id = admin_response.data[0]["id"]

        # Now try to read that row as user_a — RLS should silently hide it
        response = (
            user_a_client.table("conversations")
            .select("*")
            .eq("id", user_b_row_id)
            .execute()
        )
        assert response.data == [], (
            f"user_a was able to read user_b's row (id={user_b_row_id}). "
            "RLS isolation has FAILED."
        )

    def test_service_key_sees_all(
        self, service_client: Client, credentials: dict
    ) -> None:
        """Service key → query conversations → sees rows for all users (admin access)."""
        user_a_id = credentials["user_a"]["user_id"]
        user_b_id = credentials["user_b"]["user_id"]

        response = service_client.table("conversations").select("*").execute()
        rows = response.data

        owner_ids = {row["user_id"] for row in rows}
        assert user_a_id in owner_ids, (
            "Service key should see user_a rows but did not"
        )
        assert user_b_id in owner_ids, (
            "Service key should see user_b rows but did not"
        )

    def test_insert_enforces_user_id(
        self, user_a_client: Client, credentials: dict
    ) -> None:
        """user_a JWT → INSERT a row with user_b's user_id → should fail (RLS WITH CHECK).

        The WITH CHECK clause on the policy ensures that even on INSERT/UPDATE,
        the user_id column must match auth.uid(). Attempting to spoof another
        user's ID must raise an error or be rejected.
        """
        user_b_id = credentials["user_b"]["user_id"]

        with pytest.raises(Exception) as exc_info:
            user_a_client.table("conversations").insert(
                {
                    "user_id": user_b_id,  # Attempting to spoof user_b
                    "title": "Spoofed row",
                    "source": "spike4-rls-test",
                    "meeting_date": datetime.now(tz=UTC).isoformat(),
                }
            ).execute()

        error_message = str(exc_info.value).lower()
        # Supabase/PostgREST raises a 403 or a RLS policy violation
        assert any(
            keyword in error_message
            for keyword in ("violates", "policy", "403", "forbidden", "rls", "check")
        ), (
            f"Expected an RLS violation error but got: {exc_info.value}"
        )
