"""Shared commitment validation helpers for MVP action-item quality."""

from __future__ import annotations

import re
from typing import Any

_TOKEN_RE = re.compile(r"[a-zA-Z0-9]+")
_WHITESPACE_RE = re.compile(r"\s+")


def _normalize_text(value: str | None) -> str:
    if not value:
        return ""
    return _WHITESPACE_RE.sub(" ", value).strip()


def is_structurally_valid_commitment(text: str | None, owner: str | None) -> bool:
    normalized_text = _normalize_text(text)
    normalized_owner = _normalize_text(owner)
    if not normalized_text or not normalized_owner:
        return False
    if normalized_text.endswith("?"):
        return False

    text_tokens = _TOKEN_RE.findall(normalized_text.lower())
    owner_tokens = set(_TOKEN_RE.findall(normalized_owner.lower()))
    if len(text_tokens) < 3:
        return False

    non_owner_tokens = [token for token in text_tokens if token not in owner_tokens]
    return len(non_owner_tokens) >= 2


def sanitize_commitment_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sanitized: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str]] = set()

    for row in rows:
        owner = _normalize_text(str(row.get("owner") or ""))
        text = _normalize_text(str(row.get("text") or ""))
        if not is_structurally_valid_commitment(text, owner):
            continue

        dedupe_key = (owner.lower(), text.lower())
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)

        sanitized.append({**row, "owner": owner, "text": text})

    return sanitized
