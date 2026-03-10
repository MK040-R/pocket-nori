"""
Google OAuth2 routes.

GET  /auth/login     — redirects the browser to the Google consent screen.
GET  /auth/callback  — exchanges the authorization code for tokens, sets
                       an HttpOnly session cookie, and redirects to the frontend.
GET  /auth/session   — returns the current user's id and email (requires session).
POST /auth/logout    — clears the session cookie.
"""

import logging
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import RedirectResponse
from supabase import create_client

from src.api.deps import get_current_user
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

# Session cookie lifetime: 1 hour (matches Supabase default JWT expiry)
_SESSION_COOKIE_MAX_AGE = 3600


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
) -> RedirectResponse:
    """
    Handle the OAuth2 callback from Google.

    1. Raises HTTP 400 if Google returned an error.
    2. Exchanges the authorization code for tokens.
    3. Signs the user in to Supabase with the id_token.
    4. Sets an HttpOnly session cookie containing the Supabase JWT.
    5. Redirects the browser to the frontend onboarding page.
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
    google_access_token: str | None = token_data.get("access_token")
    google_refresh_token: str | None = token_data.get("refresh_token")

    user_index_row: dict[str, Any] = {
        "user_id": str(user.id),
        "conversation_count": 0,
        "topic_count": 0,
        "commitment_count": 0,
        "last_updated": datetime.now(tz=UTC).isoformat(),
    }
    if google_access_token:
        user_index_row["google_access_token"] = google_access_token
    if google_refresh_token:
        user_index_row["google_refresh_token"] = google_refresh_token

    try:
        user_db = get_client(session.access_token)
        user_db.table("user_index").upsert(user_index_row, on_conflict="user_id").execute()
    except Exception as exc:
        # Non-fatal: token storage failing should not block login.
        logger.error("Failed to upsert user_index for user=%s: %s", user.id, type(exc).__name__)

    # --- Set HttpOnly session cookie and redirect to frontend ---
    redirect = RedirectResponse(url=f"{settings.FRONTEND_URL}/onboarding")
    redirect.set_cookie(
        key="session",
        value=session.access_token,
        httponly=True,
        samesite="none",
        secure=True,
        max_age=_SESSION_COOKIE_MAX_AGE,
        path="/",
    )
    return redirect


@router.get("/session")
async def get_session(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Return the current user's id and email.

    Requires a valid session cookie or Authorization header.
    Returns 401 if not authenticated.
    """
    return {
        "user_id": current_user["sub"],
        "email": current_user.get("email", ""),
    }


@router.post("/logout")
async def logout(response: Response) -> dict[str, bool]:
    """Clear the session cookie and sign the user out.

    Always returns 200 — even if the user was not logged in.
    """
    response.delete_cookie(key="session", path="/")
    return {"ok": True}
