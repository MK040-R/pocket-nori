"""
Search route — semantic search across transcript segments using pgvector.

POST /search
    body: { q: str, limit?: int }
    → [{ segment_id, text, conversation_id, conversation_title, meeting_date, score }]

How it works:
  1. Embed the query string via OpenAI text-embedding-3-small
  2. Run cosine similarity search in pgvector against transcript_segments.embedding
  3. Filter strictly by user_id (enforced even though psycopg2 bypasses RLS)
  4. Join conversations to return meeting metadata alongside each result

The query text is never logged. Only result counts and user_id are logged.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from src import llm_client
from src.api.deps import get_current_user
from src.database import get_direct_connection

logger = logging.getLogger(__name__)

router = APIRouter()

_DEFAULT_LIMIT = 10
_MAX_LIMIT = 50


def _semantic_search(
    user_id: str,
    query_vector: list[float],
    limit: int,
) -> list[SearchResult]:
    vector_literal = "[" + ",".join(str(v) for v in query_vector) + "]"
    sql = """
        SELECT
            ts.id            AS segment_id,
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
        ORDER BY ts.embedding <=> %s::vector
        LIMIT %s
    """
    conn = get_direct_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (vector_literal, user_id, user_id, vector_literal, limit))
            rows = cur.fetchall()
    finally:
        conn.close()

    return [
        SearchResult(
            segment_id=str(row["segment_id"]),
            text=row["text"],
            conversation_id=str(row["conversation_id"]),
            conversation_title=row["conversation_title"],
            meeting_date=str(row["meeting_date"]),
            score=float(row["score"]),
        )
        for row in rows
    ]


def _lexical_search(user_id: str, query: str, limit: int) -> list[SearchResult]:
    sql = """
        WITH search_query AS (
            SELECT websearch_to_tsquery('simple', %s) AS query
        )
        SELECT
            ts.id            AS segment_id,
            ts.text          AS text,
            ts.conversation_id,
            c.title          AS conversation_title,
            c.meeting_date   AS meeting_date,
            ts_rank_cd(
                to_tsvector('simple', coalesce(c.title, '') || ' ' || coalesce(ts.text, '')),
                search_query.query
            ) AS score
        FROM transcript_segments ts
        JOIN conversations c
          ON c.id = ts.conversation_id
         AND c.user_id = %s
        CROSS JOIN search_query
        WHERE ts.user_id = %s
          AND to_tsvector('simple', coalesce(c.title, '') || ' ' || coalesce(ts.text, ''))
              @@ search_query.query
        ORDER BY score DESC, c.meeting_date DESC
        LIMIT %s
    """
    conn = get_direct_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (query, user_id, user_id, limit))
            rows = cur.fetchall()
    finally:
        conn.close()

    return [
        SearchResult(
            segment_id=str(row["segment_id"]),
            text=row["text"],
            conversation_id=str(row["conversation_id"]),
            conversation_title=row["conversation_title"],
            meeting_date=str(row["meeting_date"]),
            score=float(row["score"]),
        )
        for row in rows
    ]


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class SearchRequest(BaseModel):
    q: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=_DEFAULT_LIMIT, ge=1, le=_MAX_LIMIT)


class SearchResult(BaseModel):
    segment_id: str
    text: str
    conversation_id: str
    conversation_title: str
    meeting_date: str
    score: float  # 0.0 (least similar) → 1.0 (most similar)


# ---------------------------------------------------------------------------
# POST /search
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=list[SearchResult],
    summary="Semantic search across all your meeting transcript segments",
)
def search(
    body: SearchRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> list[SearchResult]:
    """Embed the query and run cosine similarity search against stored segment embeddings.

    Returns up to ``limit`` segments ranked by relevance, each with its source
    conversation metadata.

    If no segments have been embedded yet (nothing imported), returns an empty list.
    The query text is never logged.
    """
    user_id: str = current_user["sub"]

    semantic_results: list[SearchResult] = []

    # --- Embed the search query ---
    try:
        vectors = llm_client.embed_texts([body.q])
    except Exception as exc:
        logger.warning(
            "Embedding failed for search query — user=%s fallback=lexical error=%s",
            user_id,
            type(exc).__name__,
        )
    else:
        try:
            semantic_results = _semantic_search(user_id, vectors[0], body.limit)
        except Exception as exc:
            logger.warning(
                "Semantic search query failed — user=%s fallback=lexical error=%s",
                user_id,
                type(exc).__name__,
            )

    if semantic_results:
        results = semantic_results
    else:
        try:
            results = _lexical_search(user_id, body.q, body.limit)
        except Exception as exc:
            logger.error(
                "Lexical fallback failed for search query — user=%s: %s",
                user_id,
                type(exc).__name__,
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Search service temporarily unavailable.",
            ) from exc

    logger.info(
        "Search complete — user=%s results=%d mode=%s",
        user_id,
        len(results),
        "semantic" if semantic_results else "lexical",
    )
    return results
