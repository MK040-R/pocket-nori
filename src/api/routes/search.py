"""
Search route — intelligent multi-table semantic search using pre-stored embeddings.

POST /search
    body: { q: str, limit?: int, date_from?: str, date_to?: str }
    → [{ result_id, result_type, title, text, conversation_id, conversation_title,
         meeting_date, score }]

How it works:
  1. Embed the query string via OpenAI text-embedding-3-small (the only LLM cost per query)
  2. Run cosine similarity search against THREE pre-stored embedding tables:
       a. topic nodes             — semantic understanding of recurring topics
       b. entities.embedding      — people, projects, companies, products
       c. conversations.digest_embedding — LLM-generated meeting digest
  3. Also run segment-level vector search as supporting evidence
  4. Merge all results, rank by similarity score, return top limit

All embeddings are generated once at ingest time (zero LLM tokens per search query).
The query text is never logged.

POST /search/ask
    body: { q: str, date_from?: str, date_to?: str }
    → { answer: str, citations: [...] }

Retrieves top-K context via multi-table search, then calls Claude to synthesise
a direct answer with inline citations. One LLM call per user-initiated question.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, model_validator

from src import llm_client
from src.api.deps import get_current_user
from src.database import get_direct_connection
from src.entity_node_store import search_entity_node_rows
from src.topic_node_store import search_topic_node_rows

logger = logging.getLogger(__name__)

router = APIRouter()

_DEFAULT_LIMIT = 10
_MAX_LIMIT = 50
_SCORE_THRESHOLD = 0.30  # Minimum cosine similarity to include a result
_ASK_CONTEXT_LIMIT = 8  # Number of results to feed into Q&A context


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class SearchRequest(BaseModel):
    q: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=_DEFAULT_LIMIT, ge=1, le=_MAX_LIMIT)
    date_from: str | None = Field(default=None, description="ISO date YYYY-MM-DD, inclusive")
    date_to: str | None = Field(default=None, description="ISO date YYYY-MM-DD, inclusive")

    @model_validator(mode="after")
    def validate_dates(self) -> SearchRequest:
        for field_name in ("date_from", "date_to"):
            value = getattr(self, field_name)
            if value is not None:
                try:
                    date.fromisoformat(value)
                except ValueError as exc:
                    raise ValueError(
                        f"{field_name} must be a valid ISO date (YYYY-MM-DD), got: {value!r}"
                    ) from exc
        if self.date_from and self.date_to:
            if date.fromisoformat(self.date_from) > date.fromisoformat(self.date_to):
                raise ValueError("date_from must not be after date_to")
        return self


class SearchResult(BaseModel):
    result_id: str
    result_type: Literal["topic", "entity", "meeting", "segment"]
    title: str
    text: str
    conversation_id: str
    conversation_title: str
    meeting_date: str
    score: float


class AskRequest(BaseModel):
    q: str = Field(min_length=1, max_length=500)
    date_from: str | None = Field(default=None)
    date_to: str | None = Field(default=None)

    @model_validator(mode="after")
    def validate_dates(self) -> AskRequest:
        for field_name in ("date_from", "date_to"):
            value = getattr(self, field_name)
            if value is not None:
                try:
                    date.fromisoformat(value)
                except ValueError as exc:
                    raise ValueError(
                        f"{field_name} must be a valid ISO date (YYYY-MM-DD), got: {value!r}"
                    ) from exc
        if self.date_from and self.date_to:
            if date.fromisoformat(self.date_from) > date.fromisoformat(self.date_to):
                raise ValueError("date_from must not be after date_to")
        return self


class AskResponse(BaseModel):
    answer: str
    citations: list[llm_client.CitationRef]


# ---------------------------------------------------------------------------
# Private search helpers — each returns SearchResult list
# ---------------------------------------------------------------------------


def _build_vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(str(v) for v in vector) + "]"


def _date_clauses(date_from: str | None, date_to: str | None) -> tuple[str, list[Any]]:
    """Return extra SQL clauses and params for optional date range filtering."""
    clauses: list[str] = []
    params: list[Any] = []
    if date_from:
        clauses.append("AND c.meeting_date >= %s")
        params.append(date_from)
    if date_to:
        clauses.append("AND c.meeting_date <= %s")
        params.append(date_to)
    return (" ".join(clauses), params)


def _search_topic_nodes(
    user_id: str,
    query_vector: list[float],
    limit: int,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[SearchResult]:
    """Vector search against the canonical topic node abstraction."""
    conn = get_direct_connection()
    try:
        rows = search_topic_node_rows(
            user_id,
            query_vector,
            limit,
            date_from=date_from,
            date_to=date_to,
            score_threshold=_SCORE_THRESHOLD,
            conn=conn,
        )
    finally:
        conn.close()

    return [
        SearchResult(
            result_id=str(row["result_id"]),
            result_type="topic",
            title=row["title"],
            text=row["text"],
            conversation_id=str(row["conversation_id"]),
            conversation_title=row["conversation_title"],
            meeting_date=str(row["meeting_date"]),
            score=float(row["score"]),
        )
        for row in rows
    ]


def _search_entities(
    user_id: str,
    query_vector: list[float],
    limit: int,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[SearchResult]:
    """Vector search against canonical entity nodes."""
    conn = get_direct_connection()
    try:
        rows = search_entity_node_rows(
            user_id,
            query_vector,
            limit,
            date_from=date_from,
            date_to=date_to,
            score_threshold=_SCORE_THRESHOLD,
            conn=conn,
        )
    finally:
        conn.close()

    return [
        SearchResult(
            result_id=str(row["result_id"]),
            result_type="entity",
            title=row["title"],
            text=f"{row['title']} ({row['text']})",
            conversation_id=str(row["conversation_id"]),
            conversation_title=row["conversation_title"],
            meeting_date=str(row["meeting_date"]),
            score=float(row["score"]),
        )
        for row in rows
    ]


def _search_meeting_digests(
    user_id: str,
    query_vector: list[float],
    limit: int,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[SearchResult]:
    """Vector search against conversations.digest_embedding."""
    vector_literal = _build_vector_literal(query_vector)
    date_sql, date_params = _date_clauses(date_from, date_to)

    sql = f"""
        SELECT
            c.id                    AS result_id,
            c.title                 AS title,
            coalesce(c.digest, '') AS text,
            c.id                    AS conversation_id,
            c.title                 AS conversation_title,
            c.meeting_date          AS meeting_date,
            1 - (c.digest_embedding <=> %s::vector) AS score
        FROM conversations c
        WHERE c.user_id = %s
          AND c.digest_embedding IS NOT NULL
          AND 1 - (c.digest_embedding <=> %s::vector) >= %s
          {date_sql}
        ORDER BY score DESC, c.meeting_date DESC
        LIMIT %s
    """
    params: list[Any] = [vector_literal, user_id, vector_literal, _SCORE_THRESHOLD]
    params.extend(date_params)
    params.append(limit)

    conn = get_direct_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
    finally:
        conn.close()

    return [
        SearchResult(
            result_id=str(row["result_id"]),
            result_type="meeting",
            title=row["title"],
            text=row["text"],
            conversation_id=str(row["conversation_id"]),
            conversation_title=row["conversation_title"],
            meeting_date=str(row["meeting_date"]),
            score=float(row["score"]),
        )
        for row in rows
    ]


def _search_segments(
    user_id: str,
    query_vector: list[float],
    limit: int,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[SearchResult]:
    """Vector search against transcript_segments.embedding (supporting evidence layer)."""
    vector_literal = _build_vector_literal(query_vector)
    date_sql, date_params = _date_clauses(date_from, date_to)

    sql = f"""
        SELECT
            ts.id            AS result_id,
            ts.text          AS text,
            ts.conversation_id,
            c.title          AS conversation_title,
            c.meeting_date   AS meeting_date,
            1 - (ts.embedding <=> %s::vector) AS score
        FROM transcript_segments ts
        JOIN conversations c
          ON c.id = ts.conversation_id
         AND c.user_id = %s
        WHERE ts.user_id = %s
          AND ts.embedding IS NOT NULL
          AND 1 - (ts.embedding <=> %s::vector) >= %s
          {date_sql}
        ORDER BY ts.embedding <=> %s::vector
        LIMIT %s
    """
    params: list[Any] = [vector_literal, user_id, user_id, vector_literal, _SCORE_THRESHOLD]
    params.extend(date_params)
    params.extend([vector_literal, limit])

    conn = get_direct_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
    finally:
        conn.close()

    return [
        SearchResult(
            result_id=str(row["result_id"]),
            result_type="segment",
            title=row["conversation_title"],
            text=row["text"],
            conversation_id=str(row["conversation_id"]),
            conversation_title=row["conversation_title"],
            meeting_date=str(row["meeting_date"]),
            score=float(row["score"]),
        )
        for row in rows
    ]


def _merge_and_rank(
    *result_lists: list[SearchResult],
    limit: int,
) -> list[SearchResult]:
    """Merge multiple result lists, deduplicate by (result_type, result_id), sort by score."""
    seen: set[tuple[str, str]] = set()
    merged: list[SearchResult] = []
    for results in result_lists:
        for result in results:
            key = (result.result_type, result.result_id)
            if key not in seen:
                seen.add(key)
                merged.append(result)
    merged.sort(key=lambda r: r.score, reverse=True)
    return merged[:limit]


# ---------------------------------------------------------------------------
# POST /search/ask  (must be registered before POST "" to avoid path conflicts)
# ---------------------------------------------------------------------------


@router.post(
    "/ask",
    response_model=AskResponse,
    summary="Ask a natural language question answered from your meeting history",
)
def ask(
    body: AskRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> AskResponse:
    """Retrieve relevant context via multi-table search, then synthesise a direct answer.

    The question is used to embed and retrieve context — one embedding API call and
    one Claude call are made per request. The question text is never logged.
    """
    user_id: str = current_user["sub"]

    # --- Retrieve context via multi-table vector search ---
    context_results: list[SearchResult] = []
    try:
        vectors = llm_client.embed_texts([body.q])
        query_vector = vectors[0]

        topics = _search_topic_nodes(
            user_id, query_vector, _ASK_CONTEXT_LIMIT, body.date_from, body.date_to
        )
        entities = _search_entities(
            user_id, query_vector, _ASK_CONTEXT_LIMIT, body.date_from, body.date_to
        )
        meetings = _search_meeting_digests(
            user_id, query_vector, _ASK_CONTEXT_LIMIT, body.date_from, body.date_to
        )
        segments = _search_segments(
            user_id, query_vector, _ASK_CONTEXT_LIMIT, body.date_from, body.date_to
        )
        context_results = _merge_and_rank(
            topics, entities, meetings, segments, limit=_ASK_CONTEXT_LIMIT
        )
    except Exception as exc:
        logger.warning(
            "Context retrieval failed for /ask — user=%s error=%s", user_id, type(exc).__name__
        )

    if not context_results:
        return AskResponse(
            answer="I don't have enough context from your meetings to answer that question.",
            citations=[],
        )

    # --- Synthesise answer via Claude ---
    context_dicts = [r.model_dump() for r in context_results]
    try:
        result = llm_client.answer_question(body.q, context_dicts)
    except Exception as exc:
        logger.error("Answer generation failed — user=%s error=%s", user_id, type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Answer generation temporarily unavailable.",
        ) from exc

    logger.info("Ask complete — user=%s context_results=%d", user_id, len(context_results))
    return AskResponse(answer=result.answer, citations=result.citations)


# ---------------------------------------------------------------------------
# POST /search
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=list[SearchResult],
    summary="Semantic search across topics, entities, meetings, and transcripts",
)
def search(
    body: SearchRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> list[SearchResult]:
    """Embed the query and run cosine similarity search against pre-stored intelligence.

    Searches across topic nodes, entities, meeting digests, and transcript segments.
    All embeddings were computed at ingest time — zero LLM tokens consumed per query.

    Returns up to ``limit`` results ranked by relevance. Results below the similarity
    threshold (0.30) are excluded. The query text is never logged.
    """
    user_id: str = current_user["sub"]

    # --- Embed the query (only LLM-adjacent cost at query time) ---
    try:
        vectors = llm_client.embed_texts([body.q])
    except Exception as exc:
        logger.error(
            "Embedding failed for search query — user=%s error=%s",
            user_id,
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Search service temporarily unavailable.",
        ) from exc

    query_vector = vectors[0]
    date_from = body.date_from
    date_to = body.date_to

    # --- Run all four search helpers ---
    topics: list[SearchResult] = []
    entities: list[SearchResult] = []
    meetings: list[SearchResult] = []
    segments: list[SearchResult] = []

    try:
        topics = _search_topic_nodes(user_id, query_vector, body.limit, date_from, date_to)
    except Exception as exc:
        logger.warning(
            "Topic node search failed — user=%s error=%s", user_id, type(exc).__name__
        )

    try:
        entities = _search_entities(user_id, query_vector, body.limit, date_from, date_to)
    except Exception as exc:
        logger.warning("Entity search failed — user=%s error=%s", user_id, type(exc).__name__)

    try:
        meetings = _search_meeting_digests(user_id, query_vector, body.limit, date_from, date_to)
    except Exception as exc:
        logger.warning(
            "Meeting digest search failed — user=%s error=%s", user_id, type(exc).__name__
        )

    try:
        segments = _search_segments(user_id, query_vector, body.limit, date_from, date_to)
    except Exception as exc:
        logger.warning("Segment search failed — user=%s error=%s", user_id, type(exc).__name__)

    results = _merge_and_rank(topics, entities, meetings, segments, limit=body.limit)

    logger.info(
        "Search complete — user=%s results=%d (topics=%d entities=%d meetings=%d segments=%d)",
        user_id,
        len(results),
        len(topics),
        len(entities),
        len(meetings),
        len(segments),
    )
    return results
