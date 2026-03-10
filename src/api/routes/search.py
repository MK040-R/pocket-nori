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

    # --- Embed the search query ---
    try:
        vectors = llm_client.embed_texts([body.q])
    except Exception as exc:
        logger.error("Embedding failed for search query — user=%s: %s", user_id, type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Search service temporarily unavailable.",
        ) from exc

    query_vector = vectors[0]
    # Format vector as a Postgres literal: '[0.1,0.2,...]'
    vector_literal = "[" + ",".join(str(v) for v in query_vector) + "]"

    # --- pgvector cosine similarity search ---
    # user_id filter is applied BEFORE the ANN index scan (WHERE clause).
    # score = 1 - cosine_distance  (pgvector <=> returns distance, not similarity)
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
            cur.execute(
                sql,
                (vector_literal, user_id, user_id, vector_literal, body.limit),
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    results = [
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

    logger.info(
        "Search complete — user=%s results=%d",
        user_id,
        len(results),
    )
    return results
