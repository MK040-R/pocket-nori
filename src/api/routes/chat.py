"""
Chat routes — multi-turn conversational Q&A over the user's meeting history.

POST /chat                              — SSE streaming chat endpoint
GET  /chat/sessions                     — list chat sessions
GET  /chat/sessions/{session_id}/messages — paginated message history
DELETE /chat/sessions/{session_id}      — hard-delete a chat session

The chat endpoint retrieves context via the same multi-table vector search
used by POST /search/ask, then streams a Claude response with conversation
history for multi-turn context.
"""

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src import llm_client
from src.api.deps import get_current_user
from src.database import get_client, get_direct_connection

logger = logging.getLogger(__name__)

router = APIRouter()

_MAX_HISTORY_MESSAGES = 10
_CONTEXT_LIMIT = 8
_SCORE_THRESHOLD = 0.30


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    session_id: str | None = None


class ChatSessionSummary(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str
    last_message_preview: str


class ChatMessage(BaseModel):
    id: str
    role: str
    content: str
    citations: list[dict[str, Any]]
    created_at: str


class CitationOut(BaseModel):
    result_id: str
    result_type: str
    title: str
    conversation_id: str
    conversation_title: str
    meeting_date: str


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _build_vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(str(v) for v in vector) + "]"


def _retrieve_context(
    user_id: str,
    query: str,
    limit: int = _CONTEXT_LIMIT,
) -> list[dict[str, Any]]:
    """Retrieve relevant context via multi-table vector search."""
    try:
        vectors = llm_client.embed_texts([query])
    except Exception as exc:
        logger.warning("Chat context embedding failed: %s", type(exc).__name__)
        return []

    query_vector = vectors[0]
    vector_literal = _build_vector_literal(query_vector)

    conn = get_direct_connection()
    results: list[dict[str, Any]] = []
    try:
        with conn.cursor() as cur:
            # Search topic clusters
            cur.execute(
                """
                SELECT DISTINCT ON (tc.id)
                    tc.id::text AS result_id, 'topic' AS result_type,
                    tc.canonical_label AS title,
                    coalesce(tc.canonical_summary, '') AS text,
                    c.id::text AS conversation_id,
                    c.title AS conversation_title,
                    c.meeting_date::text AS meeting_date,
                    1 - (tc.embedding <=> %s::vector) AS score
                FROM topic_clusters tc
                JOIN topics t ON t.cluster_id = tc.id AND t.user_id = %s
                JOIN conversations c ON c.id = t.conversation_id AND c.user_id = %s
                WHERE tc.user_id = %s AND tc.embedding IS NOT NULL
                  AND 1 - (tc.embedding <=> %s::vector) >= %s
                ORDER BY tc.id, score DESC
                LIMIT %s
                """,
                (
                    vector_literal,
                    user_id,
                    user_id,
                    user_id,
                    vector_literal,
                    _SCORE_THRESHOLD,
                    limit,
                ),
            )
            results.extend(dict(row) for row in cur.fetchall())

            # Search meeting digests
            cur.execute(
                """
                SELECT
                    c.id::text AS result_id, 'meeting' AS result_type,
                    c.title AS title,
                    coalesce(c.digest, '') AS text,
                    c.id::text AS conversation_id,
                    c.title AS conversation_title,
                    c.meeting_date::text AS meeting_date,
                    1 - (c.digest_embedding <=> %s::vector) AS score
                FROM conversations c
                WHERE c.user_id = %s AND c.digest_embedding IS NOT NULL
                  AND 1 - (c.digest_embedding <=> %s::vector) >= %s
                ORDER BY score DESC
                LIMIT %s
                """,
                (vector_literal, user_id, vector_literal, _SCORE_THRESHOLD, limit),
            )
            results.extend(dict(row) for row in cur.fetchall())

            # Search transcript segments
            cur.execute(
                """
                SELECT
                    ts.id::text AS result_id, 'segment' AS result_type,
                    c.title AS title,
                    ts.text AS text,
                    c.id::text AS conversation_id,
                    c.title AS conversation_title,
                    c.meeting_date::text AS meeting_date,
                    1 - (ts.embedding <=> %s::vector) AS score
                FROM transcript_segments ts
                JOIN conversations c ON c.id = ts.conversation_id AND c.user_id = %s
                WHERE ts.user_id = %s AND ts.embedding IS NOT NULL
                  AND 1 - (ts.embedding <=> %s::vector) >= %s
                ORDER BY ts.embedding <=> %s::vector
                LIMIT %s
                """,
                (
                    vector_literal,
                    user_id,
                    user_id,
                    vector_literal,
                    _SCORE_THRESHOLD,
                    vector_literal,
                    limit,
                ),
            )
            results.extend(dict(row) for row in cur.fetchall())
    finally:
        conn.close()

    # Deduplicate and sort by score
    seen: set[tuple[str, str]] = set()
    deduped: list[dict[str, Any]] = []
    for r in results:
        key = (r["result_type"], r["result_id"])
        if key not in seen:
            seen.add(key)
            deduped.append(r)
    deduped.sort(key=lambda x: float(x.get("score", 0)), reverse=True)
    return deduped[:limit]


def _get_session_history(
    db: Any,
    user_id: str,
    session_id: str,
    limit: int = _MAX_HISTORY_MESSAGES,
) -> list[dict[str, str]]:
    """Fetch recent messages from a chat session for conversation context."""
    rows = (
        db.table("chat_messages")
        .select("role, content")
        .eq("session_id", session_id)
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    ).data or []
    # Reverse to get chronological order
    rows.reverse()
    return [{"role": row["role"], "content": row["content"]} for row in rows]


def _build_citations(context_results: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Build citation objects from context results."""
    citations: list[dict[str, str]] = []
    seen: set[str] = set()
    for ctx in context_results:
        conv_id = str(ctx.get("conversation_id", ""))
        if conv_id and conv_id not in seen:
            seen.add(conv_id)
            citations.append(
                {
                    "result_id": str(ctx.get("result_id", "")),
                    "result_type": str(ctx.get("result_type", "")),
                    "title": str(ctx.get("title", "")),
                    "conversation_id": conv_id,
                    "conversation_title": str(ctx.get("conversation_title", "")),
                    "meeting_date": str(ctx.get("meeting_date", "")),
                }
            )
    return citations


# ---------------------------------------------------------------------------
# POST /chat — SSE streaming
# ---------------------------------------------------------------------------


def _sse_event(event: str, data: Any) -> str:
    """Format a single SSE event."""
    json_data = json.dumps(data, default=str)
    return f"event: {event}\ndata: {json_data}\n\n"


@router.post(
    "",
    summary="Multi-turn chat with streaming response",
)
def chat(
    body: ChatRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> StreamingResponse:
    """Stream a chat response via SSE.

    Creates a new session if session_id is not provided. Retrieves relevant
    context from the user's meeting history, then streams the Claude response
    with conversation history for multi-turn context.
    """
    user_id: str = current_user["sub"]
    raw_jwt: str = current_user["_raw_jwt"]
    db = get_client(raw_jwt)

    # --- Session management ---
    session_id = body.session_id
    is_new_session = False

    if session_id:
        # Verify session belongs to user
        existing = (
            db.table("chat_sessions")
            .select("id")
            .eq("id", session_id)
            .eq("user_id", user_id)
            .execute()
        )
        if not existing.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chat session not found",
            )
    else:
        # Create new session
        session_id = str(uuid.uuid4())
        is_new_session = True
        db.table("chat_sessions").insert(
            {
                "id": session_id,
                "user_id": user_id,
                "title": "New chat",
            }
        ).execute()

    # --- Save user message ---
    db.table("chat_messages").insert(
        {
            "id": str(uuid.uuid4()),
            "session_id": session_id,
            "user_id": user_id,
            "role": "user",
            "content": body.message,
        }
    ).execute()

    # --- Retrieve context + history ---
    history = _get_session_history(db, user_id, session_id)
    # Remove the message we just saved (it's the current turn, passed separately)
    if history and history[-1]["role"] == "user" and history[-1]["content"] == body.message:
        history = history[:-1]

    context_results = _retrieve_context(user_id, body.message)
    citations = _build_citations(context_results)

    def _generate_stream():
        # Emit session ID first
        yield _sse_event("session", {"session_id": session_id})

        # Stream response
        full_response: list[str] = []
        try:
            for chunk in llm_client.stream_chat_response(
                conversation_history=history,
                context_results=context_results,
                user_message=body.message,
            ):
                full_response.append(chunk)
                yield _sse_event("delta", {"content": chunk})
        except Exception as exc:
            logger.error("Chat stream failed: %s", type(exc).__name__)
            error_msg = "I'm having trouble responding right now. Please try again."
            full_response.append(error_msg)
            yield _sse_event("delta", {"content": error_msg})

        # Emit citations
        yield _sse_event("citations", citations)

        # Save assistant message
        assistant_content = "".join(full_response)
        try:
            db.table("chat_messages").insert(
                {
                    "id": str(uuid.uuid4()),
                    "session_id": session_id,
                    "user_id": user_id,
                    "role": "assistant",
                    "content": assistant_content,
                    "citations": json.dumps(citations),
                }
            ).execute()

            # Update session timestamp
            db.table("chat_sessions").update({"updated_at": datetime.now(tz=UTC).isoformat()}).eq(
                "id", session_id
            ).eq("user_id", user_id).execute()

            # Auto-generate title for new sessions
            if is_new_session:
                try:
                    title = llm_client.generate_chat_title(body.message)
                    db.table("chat_sessions").update({"title": title}).eq("id", session_id).eq(
                        "user_id", user_id
                    ).execute()
                except Exception as title_exc:
                    logger.debug("Chat title generation skipped: %s", type(title_exc).__name__)
        except Exception as exc:
            logger.error("Failed to save assistant message: %s", type(exc).__name__)

        yield _sse_event("done", {})

    return StreamingResponse(
        _generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# GET /chat/sessions
# ---------------------------------------------------------------------------


@router.get(
    "/sessions",
    response_model=list[ChatSessionSummary],
    summary="List all chat sessions for the current user",
)
def list_sessions(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> list[ChatSessionSummary]:
    """Return chat sessions ordered by most recently updated."""
    user_id: str = current_user["sub"]
    raw_jwt: str = current_user["_raw_jwt"]
    db = get_client(raw_jwt)

    session_rows = (
        db.table("chat_sessions")
        .select("id, title, created_at, updated_at")
        .eq("user_id", user_id)
        .order("updated_at", desc=True)
        .range(offset, offset + limit - 1)
        .execute()
    ).data or []

    if not session_rows:
        return []

    # Fetch last message preview for each session
    session_ids = [str(row["id"]) for row in session_rows]
    previews: dict[str, str] = {}
    for sid in session_ids:
        msg_rows = (
            db.table("chat_messages")
            .select("content")
            .eq("session_id", sid)
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        ).data or []
        if msg_rows:
            content = str(msg_rows[0].get("content", ""))
            previews[sid] = content[:100]
        else:
            previews[sid] = ""

    return [
        ChatSessionSummary(
            id=str(row["id"]),
            title=str(row.get("title") or "New chat"),
            created_at=str(row.get("created_at", "")),
            updated_at=str(row.get("updated_at", "")),
            last_message_preview=previews.get(str(row["id"]), ""),
        )
        for row in session_rows
    ]


# ---------------------------------------------------------------------------
# GET /chat/sessions/{session_id}/messages
# ---------------------------------------------------------------------------


@router.get(
    "/sessions/{session_id}/messages",
    response_model=list[ChatMessage],
    summary="Get message history for a chat session",
)
def get_session_messages(
    session_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> list[ChatMessage]:
    """Return messages for a chat session in chronological order."""
    user_id: str = current_user["sub"]
    raw_jwt: str = current_user["_raw_jwt"]
    db = get_client(raw_jwt)

    # Verify session ownership
    session_rows = (
        db.table("chat_sessions").select("id").eq("id", session_id).eq("user_id", user_id).execute()
    )
    if not session_rows.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat session not found",
        )

    msg_rows = (
        db.table("chat_messages")
        .select("id, role, content, citations, created_at")
        .eq("session_id", session_id)
        .eq("user_id", user_id)
        .order("created_at")
        .range(offset, offset + limit - 1)
        .execute()
    ).data or []

    return [
        ChatMessage(
            id=str(row["id"]),
            role=str(row["role"]),
            content=str(row["content"]),
            citations=row.get("citations") or [],
            created_at=str(row.get("created_at", "")),
        )
        for row in msg_rows
    ]


# ---------------------------------------------------------------------------
# DELETE /chat/sessions/{session_id}
# ---------------------------------------------------------------------------


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a chat session and all its messages",
)
def delete_session(
    session_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> None:
    """Hard-delete a chat session and all its messages (cascade)."""
    user_id: str = current_user["sub"]
    raw_jwt: str = current_user["_raw_jwt"]
    db = get_client(raw_jwt)

    # Verify ownership
    existing = (
        db.table("chat_sessions").select("id").eq("id", session_id).eq("user_id", user_id).execute()
    )
    if not existing.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat session not found",
        )

    # Messages cascade on session delete
    db.table("chat_sessions").delete().eq("id", session_id).eq("user_id", user_id).execute()

    logger.info("Chat session deleted — session=%s user=%s", session_id, user_id)
