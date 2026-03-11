# Coding Conventions

**Analysis Date:** 2026-03-11

## Naming Patterns

**Files:**
- Lowercase with underscores: `config.py`, `llm_client.py`, `extract.py`
- Route modules: `auth.py`, `search.py`, `conversations.py` in `src/api/routes/`
- Model modules: `conversation.py`, `topic.py`, `commitment.py` in `src/models/`
- Test files: `test_extract.py`, `test_workers.py` in `tests/`

**Functions:**
- Lowercase with underscores (PEP 8): `extract_topics()`, `get_client()`, `_get_supabase_jwks()`
- Private functions prefixed with underscore: `_make_segment()`, `_extract()`, `_raw_client()`
- Async functions use `async def`: `async def callback()`, `async def _validate_jwt()`

**Variables:**
- Lowercase with underscores for local vars: `user_id`, `conversation_id`, `topic_count`
- UPPERCASE for module-level constants: `_DEFAULT_LIMIT`, `_EMBEDDING_MODEL`, `_MAX_LIMIT`
- Prefixed with underscore for module-private constants: `_STUB_ENV`, `_GOOGLE_AUTH_ENDPOINT`

**Types:**
- PascalCase for classes: `Conversation`, `ConversationBase`, `SearchResult`
- Literals for enums: `Literal["open", "resolved"]` in model fields
- TypedDict for structured data: `class UserCredentials(TypedDict)`, `class TestCredentials(TypedDict)`

**Imports:**
- Grouped: future imports, stdlib, third-party, local
- Example order in `src/api/deps.py`:
  ```python
  from __future__ import annotations
  import asyncio
  import logging
  from typing import Any
  import httpx
  from fastapi import Depends
  from src.config import settings
  ```

## Code Style

**Formatting:**
- Tool: `ruff` (0.9.10+)
- Line length: 100 characters
- Quote style: Double quotes
- Indent: 4 spaces

**Linting:**
- Tool: `ruff` with strict rules
- Selected rules: E, W, F, I (isort), B, C4, UP, N (PEP8-naming), S (security), T20 (no print), RUF
- Ignored: S101 (assert allowed in tests), B008 (FastAPI Depends in signature)
- Per-file ignores:
  - `tests/**/*.py`: S101, S105, S106, S107, E501 (long test credential lines)
  - `src/llm_client.py`: E501 (prompt strings must not wrap)

**Type Checking:**
- Tool: `mypy` (1.14.0+)
- Mode: `strict = true`
- Required: all functions have explicit return types and parameter types
- Example from `src/config.py`:
  ```python
  class Settings(BaseSettings):
      SUPABASE_URL: str
      ENVIRONMENT: str = "development"
      ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
  ```

## Import Organization

**Order:**
1. `from __future__ import annotations` (if using forward refs)
2. Standard library imports (`asyncio`, `logging`, `json`)
3. Third-party imports (`httpx`, `fastapi`, `pydantic`)
4. Local imports (`from src.config import`, `from src.database import`)

**Path Aliases:**
- No path aliases configured — use full relative imports
- Example: `from src.api.deps import get_current_user` (not `from api.deps`)

**Barrel Files:**
- `src/models/__init__.py`: empty
- `src/api/routes/__init__.py`: re-exports all routers

## Error Handling

**Patterns:**
- Validate input immediately at function entry: `if not all([conversation_id, user_id, user_jwt]): raise ValueError(...)`
- Raise specific exceptions: `ValueError`, `RuntimeError` for business logic; `HTTPException` for API errors
- Log before raising: `logger.error("Failed to fetch JWKS: %s", type(exc).__name__)`
- Exception chaining: `raise HTTPException(...) from exc` to preserve stack
- No silent failures: every `except` block either logs, re-raises, or returns a meaningful value

**HTTP Error Responses:**
- Use `HTTPException(status_code=..., detail=...)` from FastAPI
- Common codes: 400 (validation), 401 (auth), 403 (forbidden), 404 (not found), 502 (service unavailable)
- Example from `src/api/routes/search.py`:
  ```python
  except Exception as exc:
      logger.error("Embedding failed for search query — user=%s: %s", user_id, type(exc).__name__)
      raise HTTPException(
          status_code=status.HTTP_502_BAD_GATEWAY,
          detail="Search service temporarily unavailable.",
      ) from exc
  ```

**Non-Fatal Errors:**
- Warn and continue for non-blocking operations
- Example from `src/api/routes/auth.py`:
  ```python
  except Exception as exc:
      logger.error("Failed to upsert user_index for user=%s: %s", user.id, type(exc).__name__)
      # Continue — token storage failing should not block login
  ```

## Logging

**Framework:** Python `logging` module

**Setup:**
- Configured at module entry in `src/main.py`: `logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO), format="%(asctime)s %(levelname)s %(name)s — %(message)s")`
- Each module creates its own logger: `logger = logging.getLogger(__name__)`

**Patterns:**
- Info level for state transitions: `logger.info("Extraction started — conversation=%s user=%s", conversation_id, user_id)`
- Warning level for recoverable issues: `logger.warning("No transcript segments found for conversation=%s", conversation_id)`
- Error level for exceptions: `logger.error("Embedding failed for search query — user=%s: %s", user_id, type(exc).__name__)`
- Debug level for debug info: `logger.debug("Embedding %d texts", len(texts))`
- NEVER log transcript content, user input, or API keys — only IDs and counts

**Example from `src/workers/extract.py`:**
```python
logger.info(
    "Extraction complete — conversation=%s topics=%d commitments=%d entities=%d",
    conversation_id,
    len(topic_list.topics),
    len(commitment_list.commitments),
    len(entity_list.entities),
)
```

## Comments

**When to Comment:**
- Explain the "why" when not obvious from code
- Clarify business rules: `# Session cookie lifetime: 1 hour (matches Supabase default JWT expiry)`
- Document non-standard patterns: `# auto_error=False so the dependency doesn't raise 403 when no Bearer header is present`
- Do NOT comment obvious code like `user_id = current_user["sub"]  # extract user id`

**Style:**
- Inline comments: `# comment` with single space before
- Block comments: `# --- Section header ---` for visual separation
- Section headers use leading comment with dashes: `# --------------- Section ---------------`

**Module Docstrings (RST/reStructuredText):**
```python
"""
Extraction worker — AI pipeline from transcript segments to structured knowledge.

Pipeline per conversation:
  1. Load all TranscriptSegments
  2. Concatenate texts
  3. Call LLM

Rules:
- Transcript content is NEVER logged
- user_jwt is used for all DB operations
"""
```

## Function Design

**Size:** Keep functions focused on one responsibility — if it needs "and" in the name, split it

**Parameters:**
- Use type hints for all: `def get_client(user_jwt: str) -> Client:`
- Prefer explicit parameters over **kwargs — no implicit state
- Use default values sparingly and document them

**Return Values:**
- Always include explicit return type: `-> dict[str, Any]`, `-> list[SearchResult]`, `-> None`
- Return early on validation failures rather than nested blocks
- Example from `src/workers/extract.py`:
  ```python
  if not segments:
      logger.warning("No transcript segments found...")
      db.table("conversations").update(...).execute()
      return {"conversation_id": conversation_id, "topic_count": 0, ...}
  ```

**Docstring Style (Google-style):**
```python
def extract_topics(transcript: str) -> TopicList:
    """Extract discussion topics from a transcript.

    Args:
        transcript: Raw meeting transcript text.

    Returns:
        TopicList with validated Topic objects.

    Raises:
        ValueError: If transcript is empty.
    """
```

## Module Design

**Exports:**
- Public functions have no leading underscore
- Private helpers prefixed with underscore: `_make_segment()`, `_make_db_mock()`
- Constants prefixed with underscore if module-private: `_DEFAULT_LIMIT`

**Module Structure Pattern:**
```python
"""Module docstring explaining purpose."""

import logging
from typing import Any

logger = logging.getLogger(__name__)

# --- Constants ---
_DEFAULT_LIMIT = 10

# --- Helper functions (private) ---
def _helper() -> None:
    pass

# --- Public functions ---
def public_function() -> dict[str, Any]:
    pass
```

**Pydantic Models:**
- Use `BaseModel` with `model_config = ConfigDict(from_attributes=True)` for ORM compatibility
- Separate concerns: `Base` (shared fields) → `Create` (input) → full model (output with id/timestamps)
- Example from `src/models/conversation.py`:
  ```python
  class ConversationBase(BaseModel):
      model_config = ConfigDict(from_attributes=True)
      title: str
      source: str

  class ConversationCreate(ConversationBase):
      pass

  class Conversation(ConversationBase):
      id: uuid.UUID
      user_id: uuid.UUID
      created_at: datetime.datetime
  ```

## Dependency Injection (FastAPI)

**Pattern:**
- Functions accept dependencies via `Depends()` in signature
- Dependencies are resolved before function call
- Example from `src/api/routes/search.py`:
  ```python
  def search(
      body: SearchRequest,
      current_user: dict[str, Any] = Depends(get_current_user),
  ) -> list[SearchResult]:
  ```

**Mocking in Tests:**
- Use `app.dependency_overrides[dep_fn] = lambda: mock_value` to override
- `unittest.mock.patch` does NOT work for FastAPI dependencies
- Conftest fixture shows pattern: `conftest.py` uses `app.dependency_overrides`

## Security Conventions

**Secrets:**
- NEVER hardcode API keys, tokens, connection strings
- All required config comes from environment variables defined in `src/config.py`
- Required vars raise `ValidationError` at startup if missing

**SQL Injection Prevention:**
- Use parameterized queries with `%s` placeholders
- Example from `src/api/routes/search.py`:
  ```python
  cur.execute(
      sql,
      (vector_literal, user_id, user_id, vector_literal, body.limit),
  )
  ```

**Row-Level Security:**
- Every table read/write includes `WHERE user_id = %s` or `.eq("user_id", user_id)`
- Double-check in complex queries: `src/api/routes/search.py` has `user_id` filter twice
- Never use `get_admin_client()` in API handlers or workers

---

*Convention analysis: 2026-03-11*
