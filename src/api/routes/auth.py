"""
Google OAuth2 routes.

GET /auth/login    — redirects the browser to the Google consent screen.
GET /auth/callback — exchanges the authorization code for tokens and signs
                     the user in via Supabase.
"""

import logging
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse
from supabase import create_client

from src.config import settings
from src.database import get_client

logger = logging.getLogger(__name__)

router = APIRouter()

_GOOGLE_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"  # noqa: S105

_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]


def _redirect_uri() -> str:
    return f"{settings.API_BASE_URL}/auth/callback"


@router.get("/login")
def login() -> RedirectResponse:
    """Build the Google OAuth2 authorization URL and redirect the browser to it."""
    params: dict[str, str] = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": _redirect_uri(),
        "response_type": "code",
        "scope": " ".join(_SCOPES),
        "access_type": "offline",
        "prompt": "consent",
    }
    auth_url = f"{_GOOGLE_AUTH_ENDPOINT}?{urlencode(params)}"
    logger.info("Redirecting user to Google OAuth consent screen")
    return RedirectResponse(url=auth_url)


@router.get("/callback")
async def callback(
    code: str,
    error: str | None = None,
) -> dict[str, Any]:
    """
    Handle the OAuth2 callback from Google.

    1. Raises HTTP 400 if Google returned an error.
    2. Exchanges the authorization code for tokens.
    3. Signs the user in to Supabase with the id_token.
    4. Returns access_token, refresh_token, and basic user info.
    """
    if error is not None:
        logger.warning("Google OAuth returned an error: %s", error)
        raise HTTPException(status_code=400, detail=f"OAuth error: {error}")

    # --- Exchange authorization code for tokens ---
    token_payload: dict[str, str] = {
        "code": code,
        "client_id": settings.GOOGLE_CLIENT_ID,
        "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "redirect_uri": _redirect_uri(),
        "grant_type": "authorization_code",
    }

    try:
        async with httpx.AsyncClient() as client:
            token_response = await client.post(
                _GOOGLE_TOKEN_ENDPOINT,
                data=token_payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=15.0,
            )
    except httpx.RequestError as exc:
        logger.error("HTTP request to Google token endpoint failed: %s", type(exc).__name__)
        raise HTTPException(status_code=400, detail="Token exchange failed") from exc

    if token_response.status_code != 200:
        logger.error("Google token endpoint returned status %d", token_response.status_code)
        raise HTTPException(status_code=400, detail="Token exchange failed")

    token_data: dict[str, Any] = token_response.json()
    id_token: str | None = token_data.get("id_token")

    if not id_token:
        logger.error("Google token response did not include an id_token")
        raise HTTPException(status_code=400, detail="Token exchange failed")

    # --- Sign in to Supabase with the Google id_token ---
    supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)

    try:
        auth_response = supabase.auth.sign_in_with_id_token(
            {"provider": "google", "token": id_token}
        )
    except Exception as exc:
        logger.error("Supabase sign-in failed: %s", type(exc).__name__)
        raise HTTPException(status_code=400, detail="Authentication failed") from exc

    session = auth_response.session
    user = auth_response.user

    if session is None or user is None:
        logger.error("Supabase returned no session or user after sign-in")
        raise HTTPException(status_code=400, detail="Authentication failed")

    logger.info("User authenticated successfully (user_id=%s)", user.id)

    # --- Persist Google tokens and upsert user_index ---
    # The Google access_token and refresh_token are stored so the ingest
    # pipeline can call Drive/Calendar APIs on behalf of the user.
    # The refresh_token is only issued on the first consent — only update
    # it if Google included one in this response.
    google_access_token: str | None = token_data.get("access_token")
    google_refresh_token: str | None = token_data.get("refresh_token")

    user_index_row: dict[str, Any] = {
        "user_id": str(user.id),
        "conversation_count": 0,
        "topic_count": 0,
        "commitment_count": 0,
        "last_updated": datetime.now(tz=timezone.utc).isoformat(),
    }
    if google_access_token:
        user_index_row["google_access_token"] = google_access_token
    if google_refresh_token:
        user_index_row["google_refresh_token"] = google_refresh_token

    try:
        user_db = get_client(session.access_token)
        user_db.table("user_index").upsert(
            user_index_row, on_conflict="user_id"
        ).execute()
    except Exception as exc:
        # Non-fatal: token storage failing should not block login.
        # The user can still use the app; onboarding will prompt re-auth
        # if the tokens are missing later.
        logger.error("Failed to upsert user_index for user=%s: %s", user.id, type(exc).__name__)

    return {
        "access_token": session.access_token,
        "refresh_token": session.refresh_token,
        "user": {
            "id": user.id,
            "email": user.email,
        },
    }
