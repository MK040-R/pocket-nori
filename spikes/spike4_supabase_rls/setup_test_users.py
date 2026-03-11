"""
setup_test_users.py — Creates two test users (user_a, user_b) in Supabase Auth,
inserts sample conversation rows for each, and saves their JWTs to
test_credentials.json for use in the pytest test suite.

Idempotent: checks whether each user already exists before creating.

Requirements: SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in .env
(service key has admin access and bypasses RLS).

Run once before executing the test suite:
    python setup_test_users.py
"""

import json
import logging
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv
from supabase import Client, create_client

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")

TEST_USERS = [
    {
        "email": "user_a@test.farz.app",
        "password": "TestPassword_UserA_1!",
        "label": "user_a",
        "conversations": [
            {"title": "Q1 Planning"},
            {"title": "Design Review"},
        ],
    },
    {
        "email": "user_b@test.farz.app",
        "password": "TestPassword_UserB_1!",
        "label": "user_b",
        "conversations": [
            {"title": "Budget Meeting"},
        ],
    },
]

CREDENTIALS_PATH = Path(__file__).parent / "test_credentials.json"
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def get_admin_client() -> Client:
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise OSError(
            "SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in .env"
        )
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)


def get_anon_client() -> Client:
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        raise OSError(
            "SUPABASE_URL and SUPABASE_ANON_KEY must be set in .env"
        )
    return create_client(SUPABASE_URL, SUPABASE_ANON_KEY)


def find_existing_user(admin: Client, email: str) -> dict | None:
    """Return the existing auth user record for *email*, or None."""
    result = admin.auth.admin.list_users()
    for user in result:
        if user.email == email:
            return user
    return None


def create_or_get_user(admin: Client, email: str, password: str) -> dict:
    """Create a Supabase auth user if they don't exist; return the user object."""
    existing = find_existing_user(admin, email)
    if existing:
        logger.info("  User already exists: %s (id=%s)", email, existing.id)
        return existing

    user = admin.auth.admin.create_user(
        {"email": email, "password": password, "email_confirm": True}
    )
    logger.info("  Created user: %s (id=%s)", email, user.user.id)
    return user.user


def sign_in_user(email: str, password: str) -> dict:
    """Sign in as the given user with the anon key and return the session."""
    anon = get_anon_client()
    response = anon.auth.sign_in_with_password(
        {"email": email, "password": password}
    )
    return response.session


def insert_conversations_for_user(
    admin: Client, user_id: str, conversations: list[dict]
) -> None:
    """Insert sample conversations owned by *user_id* (uses service key to bypass RLS)."""
    now = datetime.now(tz=UTC)
    for index, convo in enumerate(conversations):
        # Check whether a row with this title already exists for this user
        existing = (
            admin.table("conversations")
            .select("id")
            .eq("user_id", user_id)
            .eq("title", convo["title"])
            .execute()
        )
        if existing.data:
            logger.info("    Row already exists: '%s' — skipping", convo["title"])
            continue

        admin.table("conversations").insert(
            {
                "user_id": user_id,
                "title": convo["title"],
                "source": "spike4-rls-test",
                "meeting_date": (
                    convo.get("meeting_date")
                    or (now - timedelta(days=index + 1)).isoformat()
                ),
            }
        ).execute()
        logger.info("    Inserted row: '%s'", convo["title"])


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logger.info("=== Farz Spike 4 — Test User Setup ===\n")
    admin = get_admin_client()

    credentials: dict[str, dict] = {}

    # Load any previously saved credentials so we can update incrementally
    if CREDENTIALS_PATH.exists():
        with CREDENTIALS_PATH.open() as fh:
            try:
                credentials = json.load(fh)
            except json.JSONDecodeError:
                credentials = {}

    for spec in TEST_USERS:
        label = spec["label"]
        email = spec["email"]
        password = spec["password"]

        logger.info("[%s] %s", label, email)

        user = create_or_get_user(admin, email, password)
        user_id = user.id if hasattr(user, "id") else user["id"]

        # Insert sample rows using admin (service key) so RLS does not interfere
        logger.info("  Inserting sample conversations...")
        insert_conversations_for_user(admin, user_id, spec["conversations"])

        # Sign in to obtain a user-scoped JWT
        logger.info("  Signing in to obtain JWT...")
        session = sign_in_user(email, password)

        credentials[label] = {
            "user_id": user_id,
            "email": email,
            "access_token": session.access_token,
            "refresh_token": session.refresh_token,
        }
        logger.info("  JWT obtained.\n")

    # Persist credentials for the test suite
    with CREDENTIALS_PATH.open("w") as fh:
        json.dump(credentials, fh, indent=2)

    logger.info("Credentials written to: %s", CREDENTIALS_PATH)
    logger.info("\nSetup complete. Run the tests with:")
    logger.info("  pytest test_rls_isolation.py -v\n")


if __name__ == "__main__":
    try:
        main()
    except OSError as exc:
        logger.error("Configuration error: %s", exc)
        sys.exit(1)
