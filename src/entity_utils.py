"""Shared entity normalization and grouping helpers for MVP entity cleanup."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_WHITESPACE_RE = re.compile(r"\s+")

_BRAND_LIKE_TYPES = {"company", "product"}
_PERSON_TYPE = "person"

# Safe brand aliases for formatting/domain variants seen in pilot data.
_BRAND_CANONICAL_ALIASES = {
    "airtable": "Airtable",
    "make": "Make",
    "makecom": "Make",
    "n8": "N8N",
    "n8n": "N8N",
    "opus": "Opus",
    "opuscom": "Opus",
}


@dataclass(slots=True)
class GroupedEntity:
    name: str
    type: str
    mentions: int
    conversation_count: int


def clean_entity_name(value: str | None) -> str:
    if not value:
        return ""
    cleaned = value.replace("\u2013", "-").replace("\u2014", "-").strip()
    return _WHITESPACE_RE.sub(" ", cleaned)


def _normalized_phrase(value: str | None) -> str:
    cleaned = clean_entity_name(value).lower()
    return re.sub(r"[^\w\s]", " ", cleaned).strip()


def _compact_key(value: str | None) -> str:
    return "".join(_TOKEN_RE.findall(_normalized_phrase(value)))


def _tokens(value: str | None) -> tuple[str, ...]:
    return tuple(_TOKEN_RE.findall(_normalized_phrase(value)))


def _entity_group_type(entity_type: str) -> str:
    return "company/product" if entity_type in _BRAND_LIKE_TYPES else entity_type


def _brand_canonical_name(name: str) -> str:
    compact = _compact_key(name)
    alias = _BRAND_CANONICAL_ALIASES.get(compact)
    if alias:
        return alias
    return clean_entity_name(name)


def _build_person_alias_map(rows: list[dict[str, Any]]) -> dict[str, str]:
    full_name_candidates: dict[str, set[str]] = defaultdict(set)
    full_name_display: dict[str, str] = {}

    for row in rows:
        if str(row.get("type") or "").strip() != _PERSON_TYPE:
            continue
        name = clean_entity_name(str(row.get("name") or ""))
        token_list = _tokens(name)
        if len(token_list) < 2:
            continue
        normalized = _normalized_phrase(name)
        full_name_display[normalized] = name
        for token in token_list:
            if len(token) >= 4:
                full_name_candidates[token].add(normalized)

    alias_map: dict[str, str] = {}
    for row in rows:
        if str(row.get("type") or "").strip() != _PERSON_TYPE:
            continue
        name = clean_entity_name(str(row.get("name") or ""))
        token_list = _tokens(name)
        if len(token_list) != 1:
            continue
        token = token_list[0]
        if len(token) < 4:
            continue
        candidates = full_name_candidates.get(token, set())
        if len(candidates) == 1:
            alias_map[_normalized_phrase(name)] = next(iter(candidates))
    return alias_map


def _choose_display_name(rows: list[dict[str, Any]], group_key: tuple[str, str]) -> str:
    group_type, normalized_name = group_key
    if group_type == "company/product":
        alias = _BRAND_CANONICAL_ALIASES.get(_compact_key(normalized_name))
        if alias:
            return alias

    scored = sorted(
        (
            (
                int(row.get("mentions") or 0),
                len(_tokens(str(row.get("name") or ""))),
                len(clean_entity_name(str(row.get("name") or ""))),
                clean_entity_name(str(row.get("name") or "")),
            )
            for row in rows
            if clean_entity_name(str(row.get("name") or ""))
        ),
        reverse=True,
    )
    if not scored:
        return normalized_name
    return scored[0][3]


def _effective_group_key(
    row: dict[str, Any],
    *,
    person_aliases: dict[str, str],
) -> tuple[str, str]:
    entity_type = str(row.get("type") or "").strip()
    name = clean_entity_name(str(row.get("name") or ""))
    normalized_name = _normalized_phrase(name)

    if entity_type == _PERSON_TYPE:
        normalized_name = person_aliases.get(normalized_name, normalized_name)
    elif entity_type in _BRAND_LIKE_TYPES:
        normalized_name = _compact_key(_brand_canonical_name(name))
    return (_entity_group_type(entity_type), normalized_name)


def group_entity_rows(rows: list[dict[str, Any]]) -> list[GroupedEntity]:
    person_aliases = _build_person_alias_map(rows)
    grouped_rows: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    type_counters: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    conversation_ids: dict[tuple[str, str], set[str]] = defaultdict(set)
    mention_counts: dict[tuple[str, str], int] = defaultdict(int)

    for row in rows:
        name = clean_entity_name(str(row.get("name") or ""))
        entity_type = str(row.get("type") or "").strip()
        if not name or not entity_type:
            continue

        key = _effective_group_key(row, person_aliases=person_aliases)
        grouped_rows[key].append({**row, "name": name, "type": entity_type})
        type_counters[key][entity_type] += int(row.get("mentions") or 0)
        mention_counts[key] += int(row.get("mentions") or 0)

        conversation_id = str(row.get("conversation_id") or "").strip()
        if conversation_id:
            conversation_ids[key].add(conversation_id)

    summaries: list[GroupedEntity] = []
    for key, group in grouped_rows.items():
        dominant_type_counts = type_counters[key]
        if key[0] == "company/product":
            display_type = (
                "company/product"
                if len(dominant_type_counts) > 1
                else next(iter(dominant_type_counts), "company/product")
            )
        else:
            display_type = next(iter(dominant_type_counts), key[0])

        summaries.append(
            GroupedEntity(
                name=_choose_display_name(group, key),
                type=display_type,
                mentions=mention_counts[key],
                conversation_count=len(conversation_ids[key]),
            )
        )

    summaries.sort(key=lambda item: (-item.mentions, -item.conversation_count, item.name.lower()))
    return summaries
