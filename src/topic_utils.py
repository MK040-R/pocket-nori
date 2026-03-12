"""Shared topic normalization and clustering helpers for MVP topic quality fixes."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_WHITESPACE_RE = re.compile(r"\s+")

_TOPIC_PLACEHOLDERS = {
    "no substantive content available",
    "no extractable transcript content",
    "no transcript content available",
    "no substantive discussion captured",
    "no meaningful topics identified",
    "no meaningful topic identified",
    "no clear topic identified",
    "no clear topics identified",
}

_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "call",
    "calls",
    "content",
    "discussion",
    "discussions",
    "for",
    "from",
    "in",
    "into",
    "is",
    "it",
    "meeting",
    "meetings",
    "next",
    "of",
    "on",
    "or",
    "overview",
    "plan",
    "plans",
    "review",
    "session",
    "sessions",
    "steps",
    "strategy",
    "sync",
    "task",
    "tasks",
    "that",
    "the",
    "this",
    "to",
    "topic",
    "topics",
    "update",
    "updates",
    "via",
    "vs",
    "with",
    "workflow",
    "workflows",
}

_GENERIC_CLUSTER_TOKENS = _STOPWORDS | {
    "academy",
    "business",
    "channel",
    "channels",
    "client",
    "clients",
    "company",
    "companies",
    "consultant",
    "consultants",
    "customer",
    "customers",
    "internal",
    "market",
    "phase",
    "pricing",
    "product",
    "program",
    "programs",
    "project",
    "projects",
    "team",
    "teams",
}


@dataclass(slots=True)
class TopicCluster:
    representative_id: str
    label: str
    summary: str
    key_quotes: list[str]
    status: str
    conversation_ids: list[str]
    topic_ids: list[str]
    latest_date: str | None
    rows: list[dict[str, Any]]


def normalize_topic_label(value: str | None) -> str:
    if not value:
        return ""
    lowered = value.lower().strip()
    lowered = re.sub(r"[^\w\s]", " ", lowered)
    return _WHITESPACE_RE.sub(" ", lowered).strip()


def clean_topic_label(value: str | None) -> str:
    if not value:
        return ""
    cleaned = value.replace("\u2013", "-").replace("\u2014", "-")
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -:;,.")
    return _WHITESPACE_RE.sub(" ", cleaned).strip()


def is_placeholder_topic_label(value: str | None) -> bool:
    normalized = normalize_topic_label(value)
    return normalized in _TOPIC_PLACEHOLDERS or normalized.startswith("no substantive")


def topic_tokens(value: str | None) -> set[str]:
    cleaned = normalize_topic_label(value)
    if not cleaned:
        return set()
    return {
        token for token in _TOKEN_RE.findall(cleaned) if len(token) >= 3 and token not in _STOPWORDS
    }


def sanitize_topic_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop placeholder topics and dedupe exact labels within one conversation."""
    sanitized: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str]] = set()

    for row in rows:
        label = clean_topic_label(str(row.get("label") or ""))
        if not label or is_placeholder_topic_label(label):
            continue

        conversation_id = str(row.get("conversation_id") or "")
        dedupe_key = (conversation_id, normalize_topic_label(label))
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)

        sanitized.append({**row, "label": label})

    return sanitized


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _sort_key_for_row(row: dict[str, Any]) -> tuple[datetime, str]:
    created_at = _parse_datetime(row.get("meeting_date") or row.get("created_at"))
    return (
        created_at or datetime.min.replace(tzinfo=UTC),
        str(row.get("id") or ""),
    )


def _label_recency(rows: list[dict[str, Any]], label: str) -> datetime:
    for row in rows:
        if clean_topic_label(str(row.get("label") or "")) == label:
            return _sort_key_for_row(row)[0]
    return datetime.min.replace(tzinfo=UTC)


def _datetime_sort_score(value: datetime) -> float:
    if value == datetime.min.replace(tzinfo=UTC):
        return float("-inf")
    return value.timestamp()


def _token_overlap(left: set[str], right: set[str]) -> set[str]:
    return left & right


def _labels_should_cluster(
    left_row: dict[str, Any],
    right_row: dict[str, Any],
    token_frequency: Counter[str],
) -> bool:
    left_normalized = normalize_topic_label(left_row.get("label"))
    right_normalized = normalize_topic_label(right_row.get("label"))
    if not left_normalized or not right_normalized:
        return False
    if left_normalized == right_normalized:
        return True
    if left_normalized in right_normalized or right_normalized in left_normalized:
        return True

    left_tokens = topic_tokens(left_row.get("label"))
    right_tokens = topic_tokens(right_row.get("label"))
    if not left_tokens or not right_tokens:
        return False

    overlap = _token_overlap(left_tokens, right_tokens)
    if len(overlap) >= 2:
        return True

    if len(overlap) != 1:
        return False

    shared_token = next(iter(overlap))
    if shared_token in _GENERIC_CLUSTER_TOKENS:
        return False
    if token_frequency[shared_token] < 2:
        return False

    left_specific = left_tokens - _GENERIC_CLUSTER_TOKENS
    right_specific = right_tokens - _GENERIC_CLUSTER_TOKENS
    return len(left_specific) <= 4 and len(right_specific) <= 4


def cluster_topic_rows(rows: list[dict[str, Any]]) -> list[TopicCluster]:
    sanitized_rows = sanitize_topic_rows(rows)
    if not sanitized_rows:
        return []

    token_frequency: Counter[str] = Counter()
    for row in sanitized_rows:
        token_frequency.update(topic_tokens(row.get("label")))

    clusters: list[list[dict[str, Any]]] = []
    for row in sanitized_rows:
        placed = False
        for cluster in clusters:
            if any(_labels_should_cluster(row, existing, token_frequency) for existing in cluster):
                cluster.append(row)
                placed = True
                break
        if not placed:
            clusters.append([row])

    result: list[TopicCluster] = []
    for cluster_rows in clusters:
        sorted_rows = sorted(cluster_rows, key=_sort_key_for_row, reverse=True)
        label_counts = Counter(
            clean_topic_label(str(row.get("label") or "")) for row in sorted_rows
        )

        candidate_labels = sorted(
            label_counts,
            key=lambda label: (
                -label_counts[label],
                len(label),
                -_datetime_sort_score(_label_recency(sorted_rows, label)),
            ),
        )
        canonical_label = (
            candidate_labels[0]
            if candidate_labels
            else clean_topic_label(str(sorted_rows[0].get("label") or ""))
        )
        representative = next(
            (
                row
                for row in sorted_rows
                if clean_topic_label(str(row.get("label") or "")) == canonical_label
            ),
            sorted_rows[0],
        )

        latest_date = None
        dated_rows = [
            _parse_datetime(row.get("meeting_date") or row.get("created_at")) for row in sorted_rows
        ]
        dated_rows = [value for value in dated_rows if value is not None]
        if dated_rows:
            latest_date = max(dated_rows).isoformat()

        summary = str(representative.get("summary") or "").strip()
        key_quotes: list[str] = []
        for row in sorted_rows:
            for quote in row.get("key_quotes") or []:
                quote_text = str(quote).strip()
                if quote_text and quote_text not in key_quotes:
                    key_quotes.append(quote_text)
                if len(key_quotes) >= 4:
                    break
            if len(key_quotes) >= 4:
                break

        statuses = {str(row.get("status") or "open") for row in sorted_rows}
        status = "resolved" if statuses == {"resolved"} else "open"

        conversation_ids = sorted(
            {
                str(row.get("conversation_id") or "")
                for row in sorted_rows
                if row.get("conversation_id")
            }
        )
        topic_ids = [str(row.get("id") or "") for row in sorted_rows if row.get("id")]

        result.append(
            TopicCluster(
                representative_id=str(representative.get("id") or ""),
                label=canonical_label,
                summary=summary,
                key_quotes=key_quotes,
                status=status,
                conversation_ids=conversation_ids,
                topic_ids=topic_ids,
                latest_date=latest_date,
                rows=sorted_rows,
            )
        )

    result.sort(
        key=lambda cluster: (
            _parse_datetime(cluster.latest_date) or datetime.min.replace(tzinfo=UTC),
            cluster.label.lower(),
        ),
        reverse=True,
    )
    return result
