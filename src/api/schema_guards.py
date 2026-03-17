"""Helpers for recognizing partially-applied schema features."""

from fastapi import HTTPException, status

_SCHEMA_ERROR_MARKERS = (
    "schema cache",
    "does not exist",
    "undefined column",
    "unknown column",
    "could not find",
)


def is_missing_schema_feature(exc: Exception, *needles: str) -> bool:
    """Return True when an exception looks like a missing table/column issue."""
    message = str(exc).lower()
    if not any(marker in message for marker in _SCHEMA_ERROR_MARKERS):
        return False
    return all(needle.lower() in message for needle in needles)


def feature_unavailable(detail: str) -> HTTPException:
    """Normalized 503 for schema-backed features that are not live yet."""
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=detail,
    )
