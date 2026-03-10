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
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client, Client
from supabase.lib.client_options import ClientOptions

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
            {"title": "Q1 Planning", "content": "Discussed roadmap priorities for Q1."},
            {"title": "Design Review", "content": "Reviewed wireframes for dashboard."},
        ],
    },
    {
        "email": "user_b@test.farz.app",
        "password": "TestPassword_UserB_1!",
        "label": "user_b",
        "conversations": [
            {"title": "Budget Meeting", "content": "Allocated budget for infra spend."},
        ],
    },
]

CREDENTIALS_PATH = Path(__file__).parent / "test_credentials.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def get_admin_client() -> Client:
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise EnvironmentError(
            "SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in .env"
        )
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)


def get_anon_client() -> Client:
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        raise EnvironmentError(
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
        print(f"  User already exists: {email} (id={existing.id})")
        return existing

    user = admin.auth.admin.create_user(
        {"email": email, "password": password, "email_confirm": True}
    )
    print(f"  Created user: {email} (id={user.user.id})")
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
    for convo in conversations:
        # Check whether a row with this title already exists for this user
        existing = (
            admin.table("conversations")
            .select("id")
            .eq("user_id", user_id)
            .eq("title", convo["title"])
            .execute()
        )
        if existing.data:
            print(f"    Row already exists: '{convo['title']}' — skipping")
            continue

        admin.table("conversations").insert(
            {
                "user_id": user_id,
                "title": convo["title"],
                "content": convo.get("content"),
            }
        ).execute()
        print(f"    Inserted row: '{convo['title']}'")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    print("=== Farz Spike 4 — Test User Setup ===\n")
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

        print(f"[{label}] {email}")

        user = create_or_get_user(admin, email, password)
        user_id = user.id if hasattr(user, "id") else user["id"]

        # Insert sample rows using admin (service key) so RLS does not interfere
        print(f"  Inserting sample conversations...")
        insert_conversations_for_user(admin, user_id, spec["conversations"])

        # Sign in to obtain a user-scoped JWT
        print(f"  Signing in to obtain JWT...")
        session = sign_in_user(email, password)

        credentials[label] = {
            "user_id": user_id,
            "email": email,
            "access_token": session.access_token,
            "refresh_token": session.refresh_token,
        }
        print(f"  JWT obtained.\n")

    # Persist credentials for the test suite
    with CREDENTIALS_PATH.open("w") as fh:
        json.dump(credentials, fh, indent=2)

    print(f"Credentials written to: {CREDENTIALS_PATH}")
    print("\nSetup complete. Run the tests with:")
    print("  pytest test_rls_isolation.py -v\n")


if __name__ == "__main__":
    try:
        main()
    except EnvironmentError as exc:
        print(f"\nConfiguration error: {exc}", file=sys.stderr)
        sys.exit(1)
