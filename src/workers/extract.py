"""
Extraction worker — deterministic write path from transcript segments to structured knowledge.

Pipeline per conversation:
  1. Load all TranscriptSegments for the conversation from DB
  2. Concatenate segment texts → single transcript string
  3. Call llm_client to extract Topics, Commitments, Entities
  4. Persist topic mentions, commitments, and entities with scored segment evidence
  5. Refresh canonical topic node metadata and arcs
  6. Update conversation/index state

Rules:
- Transcript content is NEVER logged — only IDs and counts.
- user_jwt is used for all DB operations (RLS enforced, never service_role).
- No read route calls merge logic. Semantic merge checks happen only on write paths.
- Segment links are conservative: exact match, then token overlap, else no citation.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import UTC, datetime
from typing import Any, cast

from src import llm_client
from src.cache_utils import bump_user_cache_version
from src.celery_app import celery_app
from src.commitment_utils import sanitize_commitment_rows
from src.database import get_client
from src.entity_node_store import (
    assign_node_for_entity,
    assign_nodes_to_existing_entities,
    clear_user_entity_nodes,
    load_entity_node_registry,
    load_entity_nodes,
    load_rebuild_entity_source_rows,
    refresh_entity_nodes_metadata,
    stabilize_rebuilt_entity_node_ids,
)
from src.entity_utils import clean_entity_name
from src.knowledge_graph import (
    materialize_connections_for_conversation,
    materialize_conversation_graph,
)
from src.topic_node_store import (
    assign_node_for_topic,
    assign_nodes_to_existing_topics,
    clear_user_topic_nodes,
    load_recluster_source_rows,
    load_topic_node_registry,
    load_topic_nodes,
    merge_recent_topic_rows_into_nodes_semantically,
    purge_placeholder_topics,
    refresh_nodes_metadata,
    stabilize_rebuilt_node_ids,
    upsert_topic_arcs_for_nodes,
)
from src.topic_utils import sanitize_topic_rows
from src.workers.embed import refresh_entity_node_embeddings, refresh_topic_node_embeddings
from src.workers.tasks import sync_calendar_artifacts

logger = logging.getLogger(__name__)

_MATCH_TOKEN_RE = re.compile(r"[a-z0-9]+")
_WHITESPACE_RE = re.compile(r"\s+")
_TOPIC_OVERLAP_THRESHOLD = 0.5
_COMMITMENT_OVERLAP_THRESHOLD = 0.55
_ENTITY_OVERLAP_THRESHOLD = 0.75
_BRIEF_MENTION_VERB_RE = re.compile(
    r"\b(approve|approved|agreed|decide|decided|finalize|finalized|greenlit|ship|shipped|"
    r"launch|launched|move forward|moving forward|lock in|locked in|go ahead|blocked|"
    r"unblocked|rejected|reject|defer|deferred)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Compatibility aliases for older call sites/tests during the bridge.
# ---------------------------------------------------------------------------

assign_cluster_for_topic = assign_node_for_topic
assign_clusters_to_existing_topics = assign_nodes_to_existing_topics
clear_user_topic_clusters = clear_user_topic_nodes
load_cluster_registry = load_topic_node_registry
load_topic_clusters = load_topic_nodes
merge_recent_topic_rows_semantically = merge_recent_topic_rows_into_nodes_semantically
refresh_clusters_metadata = refresh_nodes_metadata
stabilize_reclustered_cluster_ids = stabilize_rebuilt_node_ids
upsert_topic_arcs_for_clusters = upsert_topic_arcs_for_nodes

assign_cluster_for_entity = assign_node_for_entity
assign_clusters_to_existing_entities = assign_nodes_to_existing_entities
clear_user_entity_clusters = clear_user_entity_nodes
load_entity_cluster_registry = load_entity_node_registry
load_entity_clusters = load_entity_nodes
refresh_entity_clusters_metadata = refresh_entity_nodes_metadata
stabilize_reclustered_entity_cluster_ids = stabilize_rebuilt_entity_node_ids


# ---------------------------------------------------------------------------
# Segment evidence helpers
# ---------------------------------------------------------------------------


def _normalize_match_text(value: str | None) -> str:
    if not value:
        return ""
    lowered = value.lower().replace("\u2013", " ").replace("\u2014", " ")
    lowered = re.sub(r"[^\w\s]", " ", lowered)
    return _WHITESPACE_RE.sub(" ", lowered).strip()


def _match_tokens(value: str | None) -> tuple[str, ...]:
    return tuple(_MATCH_TOKEN_RE.findall(_normalize_match_text(value)))


def _text_overlap_score(left: str | None, right: str | None) -> float:
    left_tokens = set(_match_tokens(left))
    right_tokens = set(_match_tokens(right))
    if not left_tokens or not right_tokens:
        return 0.0
    overlap = left_tokens & right_tokens
    if not overlap:
        return 0.0
    return len(overlap) / len(left_tokens)


def _dedupe_candidates(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = value.strip()
        normalized = _normalize_match_text(cleaned)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(cleaned)
    return deduped


def _segment_sort_key(segment: dict[str, Any]) -> tuple[int, str]:
    return (int(segment.get("start_ms") or 0), str(segment.get("id") or ""))


def _match_candidates_to_segments(
    candidates: list[str],
    segments: list[dict[str, Any]],
    *,
    exact_origin: str,
    min_overlap_score: float,
    max_matches: int,
) -> list[dict[str, Any]]:
    if not candidates or not segments:
        return []

    prepared_segments: list[dict[str, Any]] = [
        {
            "segment": segment,
            "normalized_text": _normalize_match_text(str(segment.get("text") or "")),
        }
        for segment in segments
        if segment.get("id") and str(segment.get("text") or "").strip()
    ]
    if not prepared_segments:
        return []

    matches_by_segment: dict[str, dict[str, Any]] = {}
    for candidate in _dedupe_candidates(candidates):
        normalized_candidate = _normalize_match_text(candidate)
        if not normalized_candidate:
            continue

        exact_candidates = [
            prepared
            for prepared in prepared_segments
            if normalized_candidate in prepared["normalized_text"]
        ]
        if exact_candidates:
            best_exact = min(
                exact_candidates,
                key=lambda prepared: (
                    len(prepared["normalized_text"]),
                    _segment_sort_key(prepared["segment"]),
                ),
            )
            segment = cast(dict[str, Any], best_exact["segment"])
            segment_id = str(segment.get("id") or "")
            if segment_id:
                matches_by_segment[segment_id] = {
                    "segment_id": segment_id,
                    "segment": segment,
                    "match_score": 1.0,
                    "match_origin": exact_origin,
                }
            continue

        best_overlap: dict[str, Any] | None = None
        best_score = 0.0
        for prepared in prepared_segments:
            score = _text_overlap_score(candidate, prepared["segment"].get("text"))
            if score < min_overlap_score:
                continue
            if best_overlap is None or score > best_score or (
                score == best_score
                and _segment_sort_key(cast(dict[str, Any], prepared["segment"]))
                < _segment_sort_key(cast(dict[str, Any], best_overlap["segment"]))
            ):
                best_overlap = prepared
                best_score = score

        if best_overlap is None:
            continue

        segment = cast(dict[str, Any], best_overlap["segment"])
        segment_id = str(segment.get("id") or "")
        if not segment_id:
            continue
        existing_match = matches_by_segment.get(segment_id)
        if existing_match is None or best_score > float(existing_match.get("match_score") or 0.0):
            matches_by_segment[segment_id] = {
                "segment_id": segment_id,
                "segment": segment,
                "match_score": best_score,
                "match_origin": "token_overlap",
            }

    ordered_matches = sorted(
        matches_by_segment.values(),
        key=lambda match: (
            -float(match.get("match_score") or 0.0),
            _segment_sort_key(match["segment"]),
        ),
    )
    return ordered_matches[:max_matches]


def _build_topic_segment_matches(
    topic_row: dict[str, Any],
    segments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    evidence_quotes = [
        str(value).strip()
        for value in (topic_row.get("evidence_quotes") or [])
        if str(value).strip()
    ]
    if not evidence_quotes:
        evidence_quotes = [
            str(value).strip()
            for value in (topic_row.get("key_quotes") or [])
            if str(value).strip()
        ]
    return _match_candidates_to_segments(
        evidence_quotes,
        segments,
        exact_origin="llm_quote",
        min_overlap_score=_TOPIC_OVERLAP_THRESHOLD,
        max_matches=4,
    )


def _build_commitment_segment_matches(
    commitment_row: dict[str, Any],
    segments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    evidence_quotes = [
        str(value).strip()
        for value in (commitment_row.get("evidence_quotes") or [])
        if str(value).strip()
    ]
    if not evidence_quotes:
        evidence_quotes = [str(commitment_row.get("text") or "").strip()]
    return _match_candidates_to_segments(
        evidence_quotes,
        segments,
        exact_origin="llm_quote",
        min_overlap_score=_COMMITMENT_OVERLAP_THRESHOLD,
        max_matches=4,
    )


def _entity_alias_candidates(name: str, entity_type: str) -> list[str]:
    cleaned_name = clean_entity_name(name)
    if not cleaned_name:
        return []

    aliases = [cleaned_name]
    tokens = [token for token in cleaned_name.split() if len(token) >= 4]
    if entity_type == "person" and len(tokens) >= 2:
        aliases.extend(tokens)
    elif entity_type in {"company", "product", "project"}:
        aliases.extend(tokens)
    return _dedupe_candidates(aliases)


def _build_entity_segment_matches(
    *,
    name: str,
    entity_type: str,
    segments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return _match_candidates_to_segments(
        _entity_alias_candidates(name, entity_type),
        segments,
        exact_origin="exact_substring",
        min_overlap_score=_ENTITY_OVERLAP_THRESHOLD,
        max_matches=8,
    )


def _select_brief_mention_segments(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for segment in segments:
        text = str(segment.get("text") or "").strip()
        if not text:
            continue
        token_count = len(_match_tokens(text))
        if token_count < 4 or token_count > 40:
            continue
        if not _BRIEF_MENTION_VERB_RE.search(text):
            continue
        candidates.append(segment)
    return candidates[:10]


def _extract_brief_mention_topic_rows(
    *,
    meeting_category: str | None,
    meeting_date: str,
    conversation_id: str,
    segments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if meeting_category not in {"strategy", "client"}:
        return []

    candidate_segments = _select_brief_mention_segments(segments)
    if not candidate_segments:
        return []

    snippet_context = "\n\n".join(
        f"[segment:{segment['id']}] {str(segment.get('text') or '').strip()}"
        for segment in candidate_segments
    )
    try:
        brief_mentions = llm_client.extract_brief_mentions(snippet_context)
    except Exception:
        return []

    rows: list[dict[str, Any]] = []
    for mention in brief_mentions.mentions:
        evidence_quote = str(mention.evidence_quote or "").strip()
        if not evidence_quote:
            continue
        topic_row = {
            "label": mention.label,
            "summary": mention.summary,
            "status": mention.status,
            "key_quotes": [evidence_quote],
            "evidence_quotes": [evidence_quote],
            "conversation_id": conversation_id,
            "meeting_date": meeting_date,
        }
        if not _build_topic_segment_matches(topic_row, segments):
            continue
        rows.append(topic_row)
    return rows


def _segment_link_rows(
    *,
    user_id: str,
    item_key: str,
    item_id: str,
    matches: list[dict[str, Any]],
    origin_override: str | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for match in matches:
        segment_id = str(match.get("segment_id") or "")
        if not segment_id:
            continue
        rows.append(
            {
                "user_id": user_id,
                item_key: item_id,
                "segment_id": segment_id,
                "match_score": round(float(match.get("match_score") or 0.0), 4),
                "match_origin": origin_override
                or str(match.get("match_origin") or "token_overlap"),
            }
        )
    return rows


def _delete_existing_links(
    db: Any,
    *,
    user_id: str,
    table_name: str,
    item_key: str,
    item_ids: list[str],
) -> None:
    if not item_ids:
        return
    (db.table(table_name).delete().eq("user_id", user_id).in_(item_key, item_ids).execute())


def _backfill_topic_matches(
    topic_row: dict[str, Any],
    segments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    candidates = [
        str(value).strip() for value in (topic_row.get("key_quotes") or []) if str(value).strip()
    ]
    if not candidates:
        candidates = [str(topic_row.get("label") or "").strip()]
    return _match_candidates_to_segments(
        candidates,
        segments,
        exact_origin="exact_substring",
        min_overlap_score=_TOPIC_OVERLAP_THRESHOLD,
        max_matches=4,
    )


def _backfill_commitment_matches(
    commitment_row: dict[str, Any],
    segments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return _match_candidates_to_segments(
        [str(commitment_row.get("text") or "").strip()],
        segments,
        exact_origin="exact_substring",
        min_overlap_score=_COMMITMENT_OVERLAP_THRESHOLD,
        max_matches=4,
    )


def _replace_segment_links_for_conversation(
    db: Any,
    *,
    user_id: str,
    conversation_id: str,
    segments: list[dict[str, Any]],
) -> dict[str, int]:
    topic_rows = (
        db.table("topics")
        .select("id, label, key_quotes")
        .eq("conversation_id", conversation_id)
        .eq("user_id", user_id)
        .execute()
    ).data or []
    commitment_rows = (
        db.table("commitments")
        .select("id, text, owner")
        .eq("conversation_id", conversation_id)
        .eq("user_id", user_id)
        .execute()
    ).data or []
    entity_rows = (
        db.table("entities")
        .select("id, name, type")
        .eq("conversation_id", conversation_id)
        .eq("user_id", user_id)
        .execute()
    ).data or []

    _delete_existing_links(
        db,
        user_id=user_id,
        table_name="topic_segment_links",
        item_key="topic_id",
        item_ids=[str(row.get("id") or "") for row in topic_rows if row.get("id")],
    )
    _delete_existing_links(
        db,
        user_id=user_id,
        table_name="commitment_segment_links",
        item_key="commitment_id",
        item_ids=[str(row.get("id") or "") for row in commitment_rows if row.get("id")],
    )
    _delete_existing_links(
        db,
        user_id=user_id,
        table_name="entity_segment_links",
        item_key="entity_id",
        item_ids=[str(row.get("id") or "") for row in entity_rows if row.get("id")],
    )

    topic_link_count = 0
    commitment_link_count = 0
    entity_link_count = 0

    for topic_row in topic_rows:
        topic_id = str(topic_row.get("id") or "")
        if not topic_id:
            continue
        link_rows = _segment_link_rows(
            user_id=user_id,
            item_key="topic_id",
            item_id=topic_id,
            matches=_backfill_topic_matches(topic_row, segments),
            origin_override="legacy_backfill",
        )
        if link_rows:
            db.table("topic_segment_links").insert(link_rows).execute()
            topic_link_count += len(link_rows)

    for commitment_row in commitment_rows:
        commitment_id = str(commitment_row.get("id") or "")
        if not commitment_id:
            continue
        link_rows = _segment_link_rows(
            user_id=user_id,
            item_key="commitment_id",
            item_id=commitment_id,
            matches=_backfill_commitment_matches(commitment_row, segments),
            origin_override="legacy_backfill",
        )
        if link_rows:
            db.table("commitment_segment_links").insert(link_rows).execute()
            commitment_link_count += len(link_rows)

    for entity_row in entity_rows:
        entity_id = str(entity_row.get("id") or "")
        if not entity_id:
            continue
        link_rows = _segment_link_rows(
            user_id=user_id,
            item_key="entity_id",
            item_id=entity_id,
            matches=_build_entity_segment_matches(
                name=str(entity_row.get("name") or ""),
                entity_type=str(entity_row.get("type") or ""),
                segments=segments,
            ),
            origin_override="legacy_backfill",
        )
        if link_rows:
            db.table("entity_segment_links").insert(link_rows).execute()
            entity_link_count += len(link_rows)

    return {
        "topic_links": topic_link_count,
        "commitment_links": commitment_link_count,
        "entity_links": entity_link_count,
    }


# ---------------------------------------------------------------------------
# Celery tasks
# ---------------------------------------------------------------------------


@celery_app.task(  # type: ignore[untyped-decorator]
    bind=True,
    max_retries=2,
    default_retry_delay=120,
    soft_time_limit=300,
    time_limit=420,
)
def extract_from_conversation(
    self: Any,
    conversation_id: str,
    user_id: str,
    user_jwt: str,
    google_refresh_token: str | None = None,
) -> dict[str, Any]:
    """Extract topics, commitments, and entities from a stored conversation."""
    if not all([conversation_id, user_id, user_jwt]):
        raise ValueError("conversation_id, user_id, and user_jwt are all required")

    logger.info("Extraction started — conversation=%s user=%s", conversation_id, user_id)
    db = get_client(user_jwt)

    conv_result = (
        db.table("conversations")
        .select("id, user_id, meeting_date, title")
        .eq("id", conversation_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not conv_result.data:
        raise RuntimeError(f"Conversation {conversation_id} not found for user {user_id}")

    self.update_state(state="PROGRESS", meta={"status": "loading_segments"})
    segments_result = (
        db.table("transcript_segments")
        .select("id, speaker_id, start_ms, text")
        .eq("conversation_id", conversation_id)
        .eq("user_id", user_id)
        .order("start_ms")
        .execute()
    )
    segments: list[dict[str, Any]] = segments_result.data or []

    if not segments:
        logger.warning(
            "No transcript segments found for conversation=%s — marking indexed anyway",
            conversation_id,
        )
        db.table("conversations").update({"status": "indexed"}).eq("id", conversation_id).execute()
        bump_user_cache_version(user_id)
        if google_refresh_token:
            try:
                sync_calendar_artifacts.delay(
                    user_id=user_id,
                    user_jwt=user_jwt,
                    google_refresh_token=google_refresh_token,
                    conversation_id=conversation_id,
                )
            except Exception as exc:
                logger.warning(
                    "Post-index calendar sync dispatch failed — conversation=%s user=%s error=%s",
                    conversation_id,
                    user_id,
                    type(exc).__name__,
                )
        return {
            "conversation_id": conversation_id,
            "topic_count": 0,
            "commitment_count": 0,
            "entity_count": 0,
        }

    transcript = "\n".join(f"[{seg['speaker_id']}] {seg['text']}" for seg in segments)

    self.update_state(state="PROGRESS", meta={"status": "extracting"})
    topic_list = llm_client.extract_topics(transcript)
    commitment_list = llm_client.extract_commitments(transcript)
    entity_list = llm_client.extract_entities(transcript)

    meeting_date = str(conv_result.data[0].get("meeting_date") or "")
    conv_title = str(conv_result.data[0].get("title", "") if conv_result.data else "")
    inferred_category: str | None = None
    try:
        inferred_category = llm_client.classify_meeting_category(
            conv_title,
            [topic.label for topic in topic_list.topics[:5] if not topic.is_background],
            [entity.name for entity in entity_list.entities[:5]],
        )
    except Exception as exc:
        logger.warning(
            "Category classification failed — conversation=%s error=%s",
            conversation_id,
            type(exc).__name__,
        )

    supplemental_topic_rows = _extract_brief_mention_topic_rows(
        meeting_category=inferred_category,
        meeting_date=meeting_date,
        conversation_id=conversation_id,
        segments=segments,
    )
    sanitized_topic_rows = sanitize_topic_rows(
        [
            {
                "label": topic.label,
                "summary": topic.summary,
                "status": topic.status,
                "key_quotes": topic.key_quotes,
                "evidence_quotes": topic.evidence_quotes or topic.key_quotes,
                "conversation_id": conversation_id,
                "meeting_date": meeting_date,
            }
            for topic in topic_list.topics
            if not topic.is_background
        ]
        + supplemental_topic_rows
    )
    sanitized_commitment_rows = sanitize_commitment_rows(
        [
            {
                "text": commitment.text,
                "owner": commitment.owner,
                "due_date": commitment.due_date,
                "status": commitment.status,
                "action_type": commitment.action_type,
                "evidence_quotes": commitment.evidence_quotes or [commitment.text],
            }
            for commitment in commitment_list.commitments
        ]
    )

    logger.info(
        "Extraction complete — conversation=%s topics=%d commitments=%d entities=%d",
        conversation_id,
        len(sanitized_topic_rows),
        len(sanitized_commitment_rows),
        len(entity_list.entities),
    )

    self.update_state(state="PROGRESS", meta={"status": "saving_topics"})
    topic_ids: list[str] = []
    topic_nodes = load_cluster_registry(db, user_id)
    affected_topic_node_ids: set[str] = set()

    for topic_row in sanitized_topic_rows:
        topic_node_id = assign_cluster_for_topic(
            db,
            user_id,
            topic_row=topic_row,
            nodes=topic_nodes,
        )
        topic_id = str(uuid.uuid4())
        db.table("topics").insert(
            {
                "id": topic_id,
                "user_id": user_id,
                "conversation_id": conversation_id,
                "cluster_id": topic_node_id,
                "label": topic_row["label"],
                "summary": topic_row.get("summary", ""),
                "status": topic_row.get("status", "open"),
                "key_quotes": topic_row.get("key_quotes") or [],
            }
        ).execute()
        topic_ids.append(topic_id)
        affected_topic_node_ids.add(topic_node_id)

        topic_link_rows = _segment_link_rows(
            user_id=user_id,
            item_key="topic_id",
            item_id=topic_id,
            matches=_build_topic_segment_matches(topic_row, segments),
        )
        if topic_link_rows:
            db.table("topic_segment_links").insert(topic_link_rows).execute()

    if affected_topic_node_ids:
        refresh_clusters_metadata(db, user_id, affected_topic_node_ids)
        upsert_topic_arcs_for_clusters(db, user_id, affected_topic_node_ids)

    self.update_state(state="PROGRESS", meta={"status": "saving_commitments"})
    for commitment in sanitized_commitment_rows:
        commitment_id = str(uuid.uuid4())

        due_date: str | None = None
        if commitment.get("due_date"):
            try:
                due_date = datetime.fromisoformat(str(commitment["due_date"])).isoformat()
            except ValueError:
                due_date = None

        db.table("commitments").insert(
            {
                "id": commitment_id,
                "user_id": user_id,
                "conversation_id": conversation_id,
                "text": commitment["text"],
                "owner": commitment["owner"],
                "due_date": due_date,
                "status": commitment.get("status", "open"),
                "action_type": commitment.get("action_type", "commitment"),
            }
        ).execute()

        commitment_link_rows = _segment_link_rows(
            user_id=user_id,
            item_key="commitment_id",
            item_id=commitment_id,
            matches=_build_commitment_segment_matches(commitment, segments),
        )
        if commitment_link_rows:
            db.table("commitment_segment_links").insert(commitment_link_rows).execute()

    self.update_state(state="PROGRESS", meta={"status": "saving_entities"})
    entity_nodes = load_entity_cluster_registry(db, user_id)
    affected_entity_node_ids: set[str] = set()
    for entity in entity_list.entities:
        entity_row = {
            "name": entity.name,
            "type": entity.type,
            "mentions": entity.mentions,
            "conversation_id": conversation_id,
            "meeting_date": meeting_date,
        }
        entity_node_id = assign_cluster_for_entity(
            db,
            user_id,
            entity_row=entity_row,
            nodes=entity_nodes,
            use_embedding_candidates=True,
        )
        entity_id = str(uuid.uuid4())
        db.table("entities").insert(
            {
                "id": entity_id,
                "user_id": user_id,
                "conversation_id": conversation_id,
                "entity_node_id": entity_node_id,
                "name": entity.name,
                "type": entity.type,
                "mentions": entity.mentions,
            }
        ).execute()
        affected_entity_node_ids.add(entity_node_id)

        entity_link_rows = _segment_link_rows(
            user_id=user_id,
            item_key="entity_id",
            item_id=entity_id,
            matches=_build_entity_segment_matches(
                name=entity.name,
                entity_type=entity.type,
                segments=segments,
            ),
        )
        if entity_link_rows:
            db.table("entity_segment_links").insert(entity_link_rows).execute()

    if affected_entity_node_ids:
        refresh_entity_clusters_metadata(db, user_id, affected_entity_node_ids)

    self.update_state(state="PROGRESS", meta={"status": "materializing_graph"})
    try:
        materialize_conversation_graph(db, user_id, conversation_id)
        materialize_connections_for_conversation(
            db,
            user_id,
            conversation_id,
            str(conv_result.data[0].get("title") or "This meeting"),
        )
    except Exception as exc:
        logger.warning(
            "Graph materialization failed — conversation=%s error=%s",
            conversation_id,
            type(exc).__name__,
        )

    self.update_state(state="PROGRESS", meta={"status": "generating_digest"})
    try:
        digest = llm_client.generate_meeting_digest(
            topics=[
                {"label": row["label"], "summary": row.get("summary", "")}
                for row in sanitized_topic_rows
            ],
            commitments=[
                {
                    "text": c["text"],
                    "owner": c["owner"],
                    "due_date": c.get("due_date"),
                }
                for c in sanitized_commitment_rows
            ],
            entities=[{"name": e.name, "type": e.type} for e in entity_list.entities],
        )
        if digest:
            db.table("conversations").update({"digest": digest}).eq("id", conversation_id).eq(
                "user_id", user_id
            ).execute()
            logger.info("Digest stored — conversation=%s", conversation_id)
    except Exception as exc:
        logger.warning(
            "Digest generation failed — conversation=%s error=%s",
            conversation_id,
            type(exc).__name__,
        )

    self.update_state(state="PROGRESS", meta={"status": "classifying_category"})
    if inferred_category:
        db.table("conversations").update({"category": inferred_category}).eq(
            "id", conversation_id
        ).eq("user_id", user_id).execute()
        logger.info(
            "Category classified — conversation=%s category=%s",
            conversation_id,
            inferred_category,
        )

    db.table("conversations").update({"status": "indexed"}).eq("id", conversation_id).execute()

    current_topic_node_count = len(load_topic_clusters(db, user_id, min_conversations=1))
    current_entity_count = len(load_entity_clusters(db, user_id, min_conversations=1))

    existing_index = (
        db.table("user_index")
        .select("topic_count, commitment_count")
        .eq("user_id", user_id)
        .execute()
    )
    if existing_index.data:
        current = existing_index.data[0]
        db.table("user_index").update(
            {
                "topic_count": current_topic_node_count,
                "commitment_count": current["commitment_count"] + len(sanitized_commitment_rows),
                "entity_count": current_entity_count,
                "last_updated": datetime.now(tz=UTC).isoformat(),
            }
        ).eq("user_id", user_id).execute()

    logger.info(
        "Extraction persisted — conversation=%s topics=%d commitments=%d entities=%d user=%s",
        conversation_id,
        len(sanitized_topic_rows),
        len(sanitized_commitment_rows),
        len(entity_list.entities),
        user_id,
    )
    bump_user_cache_version(user_id)

    if google_refresh_token:
        try:
            sync_calendar_artifacts.delay(
                user_id=user_id,
                user_jwt=user_jwt,
                google_refresh_token=google_refresh_token,
                conversation_id=conversation_id,
            )
        except Exception as exc:
            logger.warning(
                "Post-index calendar sync dispatch failed — conversation=%s user=%s error=%s",
                conversation_id,
                user_id,
                type(exc).__name__,
            )

    return {
        "conversation_id": conversation_id,
        "topic_count": len(sanitized_topic_rows),
        "commitment_count": len(sanitized_commitment_rows),
        "entity_count": len(entity_list.entities),
    }


@celery_app.task(  # type: ignore[untyped-decorator]
    bind=True,
    max_retries=1,
    default_retry_delay=60,
    soft_time_limit=900,
    time_limit=1200,
)
def rebuild_topic_nodes_for_user(
    self: Any,
    user_id: str,
    user_jwt: str,
) -> dict[str, Any]:
    """Rebuild durable topic nodes and arcs for a user."""
    if not all([user_id, user_jwt]):
        raise ValueError("user_id and user_jwt are both required")

    logger.info("Topic node rebuild started — user=%s", user_id)
    db = get_client(user_jwt)

    previous_topic_nodes = load_topic_clusters(db, user_id, min_conversations=1)

    self.update_state(state="PROGRESS", meta={"status": "purging_placeholders", "user_id": user_id})
    purged_count = purge_placeholder_topics(db, user_id)

    self.update_state(state="PROGRESS", meta={"status": "loading_topics", "user_id": user_id})
    topic_rows = load_recluster_source_rows(db, user_id)

    self.update_state(
        state="PROGRESS",
        meta={"status": "rebuilding_nodes_lexical", "user_id": user_id},
    )
    clear_user_topic_clusters(db, user_id)
    affected_topic_node_ids = assign_clusters_to_existing_topics(
        db,
        user_id,
        topic_rows,
        enable_semantic=False,
    )
    refreshed_topic_nodes = refresh_clusters_metadata(db, user_id, affected_topic_node_ids)
    final_topic_node_ids = {topic_node.id for topic_node in refreshed_topic_nodes}

    self.update_state(
        state="PROGRESS",
        meta={"status": "rebuilding_nodes_semantic_recent", "user_id": user_id},
    )
    recent_semantic_node_ids, semantic_check_count = merge_recent_topic_rows_semantically(
        db,
        user_id,
        topic_rows,
    )
    if recent_semantic_node_ids:
        affected_topic_node_ids.update(recent_semantic_node_ids)
        refresh_clusters_metadata(db, user_id, affected_topic_node_ids)

    final_topic_node_ids = stabilize_reclustered_cluster_ids(db, user_id, previous_topic_nodes)
    refreshed_topic_nodes = refresh_clusters_metadata(db, user_id, final_topic_node_ids)
    final_topic_node_ids = {topic_node.id for topic_node in refreshed_topic_nodes}

    self.update_state(
        state="PROGRESS",
        meta={"status": "refreshing_node_embeddings", "user_id": user_id},
    )
    refreshed_embedding_count = refresh_topic_node_embeddings(
        db,
        user_id,
        final_topic_node_ids,
    )

    self.update_state(state="PROGRESS", meta={"status": "rebuilding_arcs", "user_id": user_id})
    upsert_topic_arcs_for_clusters(
        db,
        user_id,
        final_topic_node_ids,
    )

    db.table("user_index").update(
        {
            "topic_count": len(final_topic_node_ids),
            "last_updated": datetime.now(tz=UTC).isoformat(),
        }
    ).eq("user_id", user_id).execute()

    bump_user_cache_version(user_id)
    logger.info(
        (
            "Topic node rebuild complete — user=%s topic_nodes=%d "
            "topics=%d purged=%d semantic_checks=%d embeddings=%d"
        ),
        user_id,
        len(final_topic_node_ids),
        len(topic_rows),
        purged_count,
        semantic_check_count,
        refreshed_embedding_count,
    )
    return {
        "user_id": user_id,
        "cluster_count": len(final_topic_node_ids),
        "topic_count": len(topic_rows),
        "purged_topic_count": purged_count,
        "semantic_check_count": semantic_check_count,
    }


@celery_app.task(  # type: ignore[untyped-decorator]
    bind=True,
    max_retries=1,
    default_retry_delay=60,
    soft_time_limit=900,
    time_limit=1200,
)
def rebuild_entity_nodes_for_user(
    self: Any,
    user_id: str,
    user_jwt: str,
) -> dict[str, Any]:
    """Rebuild durable entity nodes for a user."""
    if not all([user_id, user_jwt]):
        raise ValueError("user_id and user_jwt are both required")

    logger.info("Entity node rebuild started — user=%s", user_id)
    db = get_client(user_jwt)

    previous_entity_nodes = load_entity_clusters(db, user_id, min_conversations=1)

    self.update_state(state="PROGRESS", meta={"status": "loading_entities", "user_id": user_id})
    entity_rows = load_rebuild_entity_source_rows(db, user_id)

    self.update_state(
        state="PROGRESS",
        meta={"status": "rebuilding_entity_nodes", "user_id": user_id},
    )
    clear_user_entity_clusters(db, user_id)
    semantic_budget = {"used": 0, "limit": 120}
    affected_entity_node_ids = assign_clusters_to_existing_entities(
        db,
        user_id,
        entity_rows,
        enable_semantic=True,
        semantic_budget=semantic_budget,
        use_embedding_candidates=True,
    )
    refreshed_entity_nodes = refresh_entity_clusters_metadata(db, user_id, affected_entity_node_ids)
    final_entity_node_ids = {entity_node.id for entity_node in refreshed_entity_nodes}

    final_entity_node_ids = stabilize_reclustered_entity_cluster_ids(
        db,
        user_id,
        previous_entity_nodes,
    )
    refreshed_entity_nodes = refresh_entity_clusters_metadata(db, user_id, final_entity_node_ids)
    final_entity_node_ids = {entity_node.id for entity_node in refreshed_entity_nodes}

    self.update_state(
        state="PROGRESS",
        meta={"status": "refreshing_entity_node_embeddings", "user_id": user_id},
    )
    refreshed_embedding_count = refresh_entity_node_embeddings(
        db,
        user_id,
        final_entity_node_ids,
    )

    db.table("user_index").update(
        {
            "entity_count": len(final_entity_node_ids),
            "last_updated": datetime.now(tz=UTC).isoformat(),
        }
    ).eq("user_id", user_id).execute()

    bump_user_cache_version(user_id)
    logger.info(
        (
            "Entity node rebuild complete — user=%s entity_nodes=%d "
            "entities=%d semantic_checks=%d embeddings=%d"
        ),
        user_id,
        len(final_entity_node_ids),
        len(entity_rows),
        semantic_budget["used"],
        refreshed_embedding_count,
    )
    return {
        "user_id": user_id,
        "entity_node_count": len(final_entity_node_ids),
        "entity_count": len(entity_rows),
        "semantic_check_count": semantic_budget["used"],
    }


@celery_app.task(  # type: ignore[untyped-decorator]
    bind=True,
    max_retries=1,
    default_retry_delay=60,
    soft_time_limit=1200,
    time_limit=1500,
)
def backfill_knowledge_graph_for_user(
    self: Any,
    user_id: str,
    user_jwt: str,
) -> dict[str, Any]:
    """Rebuild graph edges and compatibility connections for all conversations."""
    if not all([user_id, user_jwt]):
        raise ValueError("user_id and user_jwt are both required")

    logger.info("Knowledge graph backfill started — user=%s", user_id)
    db = get_client(user_jwt)

    conversation_rows = (
        db.table("conversations")
        .select("id, title")
        .eq("user_id", user_id)
        .order("meeting_date")
        .execute()
    ).data or []

    conversations_processed = 0
    edge_count = 0
    evidence_count = 0

    for index, row in enumerate(conversation_rows, start=1):
        conversation_id = str(row.get("id") or "")
        if not conversation_id:
            continue
        self.update_state(
            state="PROGRESS",
            meta={
                "status": "backfilling_knowledge_graph",
                "user_id": user_id,
                "processed": index - 1,
                "total": len(conversation_rows),
            },
        )
        counts = materialize_conversation_graph(db, user_id, conversation_id)
        materialize_connections_for_conversation(
            db,
            user_id,
            conversation_id,
            str(row.get("title") or "This meeting"),
        )
        edge_count += counts["edge_count"]
        evidence_count += counts["evidence_count"]
        conversations_processed += 1

    bump_user_cache_version(user_id)
    logger.info(
        "Knowledge graph backfill complete — user=%s conversations=%d edges=%d evidence=%d",
        user_id,
        conversations_processed,
        edge_count,
        evidence_count,
    )
    return {
        "user_id": user_id,
        "conversations_processed": conversations_processed,
        "edge_count": edge_count,
        "evidence_count": evidence_count,
    }


@celery_app.task(  # type: ignore[untyped-decorator]
    bind=True,
    max_retries=1,
    default_retry_delay=60,
    soft_time_limit=1200,
    time_limit=1500,
)
def backfill_segment_links_for_user(
    self: Any,
    user_id: str,
    user_jwt: str,
) -> dict[str, Any]:
    """Rebuild scored segment links for existing topics, commitments, and entities."""
    if not all([user_id, user_jwt]):
        raise ValueError("user_id and user_jwt are both required")

    logger.info("Segment link backfill started — user=%s", user_id)
    db = get_client(user_jwt)

    conversation_rows = (
        db.table("conversations")
        .select("id")
        .eq("user_id", user_id)
        .order("meeting_date")
        .execute()
    ).data or []

    conversations_processed = 0
    topic_links_created = 0
    commitment_links_created = 0
    entity_links_created = 0

    for index, conversation_row in enumerate(conversation_rows, start=1):
        conversation_id = str(conversation_row.get("id") or "")
        if not conversation_id:
            continue
        self.update_state(
            state="PROGRESS",
            meta={
                "status": "backfilling_segment_links",
                "user_id": user_id,
                "processed": index - 1,
                "total": len(conversation_rows),
            },
        )
        segments = (
            db.table("transcript_segments")
            .select("id, start_ms, text")
            .eq("conversation_id", conversation_id)
            .eq("user_id", user_id)
            .order("start_ms")
            .execute()
        ).data or []
        counts = _replace_segment_links_for_conversation(
            db,
            user_id=user_id,
            conversation_id=conversation_id,
            segments=segments,
        )
        topic_links_created += counts["topic_links"]
        commitment_links_created += counts["commitment_links"]
        entity_links_created += counts["entity_links"]
        conversations_processed += 1

    topic_nodes = load_topic_clusters(db, user_id, min_conversations=1)
    if topic_nodes:
        topic_node_ids = {topic_node.id for topic_node in topic_nodes}
        upsert_topic_arcs_for_clusters(db, user_id, topic_node_ids)

    bump_user_cache_version(user_id)
    logger.info(
        (
            "Segment link backfill complete — user=%s conversations=%d "
            "topic_links=%d commitment_links=%d entity_links=%d"
        ),
        user_id,
        conversations_processed,
        topic_links_created,
        commitment_links_created,
        entity_links_created,
    )
    return {
        "user_id": user_id,
        "conversations_processed": conversations_processed,
        "topic_links_created": topic_links_created,
        "commitment_links_created": commitment_links_created,
        "entity_links_created": entity_links_created,
    }


# Backward-compatible task alias during the bridge phase.
recluster_topics_for_user = rebuild_topic_nodes_for_user
