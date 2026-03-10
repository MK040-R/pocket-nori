"""
FastAPI dependency functions shared across route handlers.
"""

import asyncio
import logging
import time
from typing import Any

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import ExpiredSignatureError, JWTError, jwt

from src.config import settings

logger = logging.getLogger(__name__)

_bearer_scheme = HTTPBearer()
_SUPPORTED_SUPABASE_JWT_ALGORITHMS = {"RS256", "ES256", "HS256"}

_jwks_cache: dict[str, dict[str, Any]] = {}
_jwks_cache_expires_at: float = 0.0
_jwks_lock = asyncio.Lock()


def _supabase_jwt_issuer() -> str:
    """Return the expected token issuer for Supabase access tokens."""
    if settings.SUPABASE_JWT_ISSUER:
        return settings.SUPABASE_JWT_ISSUER
    return f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1"


def _supabase_jwks_url() -> str:
    return f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1/.well-known/jwks.json"


async def _get_supabase_jwks(force_refresh: bool = False) -> dict[str, dict[str, Any]]:
    """Fetch and cache Supabase JWKS for JWT signature verification."""
    global _jwks_cache, _jwks_cache_expires_at

    now = time.time()
    if not force_refresh and _jwks_cache and now < _jwks_cache_expires_at:
        return _jwks_cache

    async with _jwks_lock:
        now = time.time()
        if not force_refresh and _jwks_cache and now < _jwks_cache_expires_at:
            return _jwks_cache

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(_supabase_jwks_url())
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.error("Failed to fetch Supabase JWKS: %s", type(exc).__name__)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication service unavailable",
            ) from exc

        keys = payload.get("keys")
        if not isinstance(keys, list) or not keys:
            logger.error("Supabase JWKS payload is missing usable keys")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication service unavailable",
            )

        keyed: dict[str, dict[str, Any]] = {}
        for key in keys:
            if not isinstance(key, dict):
                continue
            kid = key.get("kid")
            if isinstance(kid, str) and kid:
                keyed[kid] = key

        if not keyed:
            logger.error("Supabase JWKS payload contains no key IDs")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication service unavailable",
            )

        _jwks_cache = keyed
        _jwks_cache_expires_at = now + settings.SUPABASE_JWKS_TTL_SECONDS
        return _jwks_cache


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> dict[str, Any]:
    """
    Decode and validate the JWT supplied in the Authorization header.

    Returns the decoded payload dict (``sub`` field contains the user_id).
    Raises HTTP 401 on any validation failure — no token details are logged.
    """
    token = credentials.credentials

    try:
        header: dict[str, Any] = jwt.get_unverified_header(token)
    except JWTError as exc:
        logger.warning("JWT validation failed: malformed token header")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from exc

    algorithm = header.get("alg")
    if not isinstance(algorithm, str):
        logger.warning("JWT validation failed: missing algorithm in token header")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    if algorithm not in _SUPPORTED_SUPABASE_JWT_ALGORITHMS:
        logger.warning("JWT validation failed: unsupported algorithm")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    signing_key: str | dict[str, Any]
    if algorithm == "HS256":
        if not settings.SUPABASE_JWT_SECRET:
            logger.warning("JWT validation failed: HS256 token but SUPABASE_JWT_SECRET is unset")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
            )
        signing_key = settings.SUPABASE_JWT_SECRET
    else:
        key_id = header.get("kid")
        if not isinstance(key_id, str):
            logger.warning("JWT validation failed: missing kid in token header")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
            )
        jwks = await _get_supabase_jwks()
        signing_key_candidate = jwks.get(key_id)
        if signing_key_candidate is None:
            # Key rotation may have happened; force refresh once.
            signing_key_candidate = (await _get_supabase_jwks(force_refresh=True)).get(key_id)
        if signing_key_candidate is None:
            logger.warning("JWT validation failed: signing key not found in JWKS")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
            )
        signing_key = signing_key_candidate

    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            signing_key,
            algorithms=[algorithm],
            audience=settings.SUPABASE_JWT_AUDIENCE,
            issuer=_supabase_jwt_issuer(),
        )
        if not payload.get("sub"):
            logger.warning("JWT validation failed: missing sub claim")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
            )
        # Inject the raw bearer token so route handlers can pass it to get_client().
        payload["_raw_jwt"] = token
        return payload
    except ExpiredSignatureError as exc:
        logger.warning("JWT validation failed: token expired")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from exc
    except JWTError as exc:
        logger.warning("JWT validation failed: invalid token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from exc
