"""
LLM gateway — ALL Claude API calls must go through this module.

Rules enforced here:
- Transcript content is never logged.
- Extraction uses claude-sonnet-4-6; briefs use claude-opus-4-6.
- All extraction returns validated Pydantic objects via instructor — no raw JSON parsing.
"""

import logging
from enum import StrEnum
from typing import Any, Literal

import anthropic
import instructor
import openai
from anthropic.types import TextBlock
from pydantic import BaseModel, Field

from src.config import settings

_EMBEDDING_MODEL = "text-embedding-3-small"
_EMBEDDING_DIMENSIONS = 1536

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Extraction response models
# ---------------------------------------------------------------------------


class TopicResult(BaseModel):
    label: str = Field(description="Short topic name, 3-50 characters")
    summary: str = Field(description="1-2 sentence summary of what was discussed")
    status: Literal["open", "resolved"]
    key_quotes: list[str] = Field(default_factory=list, max_length=2)
    is_background: bool = Field(
        default=False,
        description="True only for background, introductory, administrative, or low-signal topics that should not be surfaced",
    )


class TopicList(BaseModel):
    topics: list[TopicResult]


class CommitmentResult(BaseModel):
    text: str = Field(description="The commitment statement")
    owner: str = Field(description="Name of the person who made the commitment")
    due_date: str | None = Field(
        default=None, description="ISO date YYYY-MM-DD if explicitly stated, else null"
    )
    status: Literal["open", "resolved"] = "open"


class CommitmentList(BaseModel):
    commitments: list[CommitmentResult]


class EntityResult(BaseModel):
    name: str = Field(description="Canonical name as it appears in the transcript")
    type: Literal["person", "project", "company", "product"]
    mentions: int = Field(ge=1)


class EntityList(BaseModel):
    entities: list[EntityResult]


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_TOPIC_SYSTEM_PROMPT = """You are an expert meeting analyst. Extract the meaningful work topics from a meeting transcript.

For each topic:
- Provide a short, stable, initiative-level label (3-50 characters)
- Write a 1-2 sentence summary of the substance of the discussion, not just a restatement of the label
- Determine if the topic is "open" (unresolved, needs follow-up) or "resolved" (concluded, decided)
- Include up to 2 verbatim quotes that best represent the topic
- Mark is_background=true only when the discussion is introductory, administrative, purely contextual, or not important enough to surface as a user-facing topic

Guidelines:
- Extract only topics clearly discussed — do not invent or infer topics not present
- Prefer canonical labels that remain stable across meetings even when wording changes
- Use initiative-level naming rather than one-off phrasing (e.g., "Consultant incentive structure" not "Consultant incentive structure for phase one onboarding")
- Only surface topics that are actionable, evolving, decision-bearing, or clearly owned by the user/team
- Exclude background/intro/admin material such as greetings, general catch-up, meeting logistics, recap-only context, or one-off side remarks
- A topic should represent a coherent subject of discussion, not a single passing remark
- Accuracy over quantity: 3 real topics is better than 8 weak topics
- If participants returned to a subject multiple times, treat it as one topic
- Return at most 5 topics for one meeting
- Do not return placeholders such as "No substantive content available", "No extractable transcript content", or any equivalent "no content" label"""

_COMMITMENT_SYSTEM_PROMPT = """You are an expert meeting analyst. Extract commitments and action items from a meeting transcript.

A commitment is a statement where a named participant agrees to do something:
- Explicit action items ("I'll send the report by Friday")
- Agreements to follow up ("Let me check on that and get back to you")
- Assigned tasks ("Can you own the API integration? — Sure, I'll handle it")

For each commitment:
- Capture the exact text or a close paraphrase
- Identify the person who owns it (use their name as spoken)
- Extract a due date only if explicitly mentioned (ISO format YYYY-MM-DD); leave null if not stated
- Set status to "open" unless the transcript explicitly confirms completion

Guidelines:
- Only extract commitments with a clear owner — exclude vague "we should" statements
- Exclude observations, summaries, decisions, and status updates that are not forward-looking commitments
- Keep only action items with a clear owner and a concrete intended action
- Do not fabricate due dates
- Accuracy over quantity"""

_ENTITY_SYSTEM_PROMPT = """You are an expert meeting analyst. Extract named entities from a meeting transcript.

Entity types to extract:
- person: named individuals mentioned or speaking
- project: named projects, initiatives, or workstreams
- company: organizations or teams
- product: named software products, tools, platforms, or features

For each entity:
- Use the name exactly as it appears most completely in the transcript
- Count total mentions (approximate is fine)

Guidelines:
- Only extract entities with proper names — exclude generic references ("the backend", "the client")
- If referred to by multiple names, count them together under the canonical name
- Accuracy over quantity"""

_DIGEST_SYSTEM_PROMPT = """You are a personal meeting intelligence assistant.
Given the structured data extracted from a completed meeting — topics, commitments, and entities — write a concise 3-5 sentence digest.
Capture: the main themes discussed, any key decisions made, action items assigned, and notable people or projects mentioned.
Be specific and factual. Ground every sentence in the provided data. Do not speculate or pad."""

_BRIEF_SYSTEM_PROMPT = """You are an expert meeting strategist. Given context about a person's past meetings and an upcoming calendar event, write a concise pre-meeting brief.

Include:
- A 2-3 sentence situational summary: what relevant history exists with these people or topics
- Open commitments from previous meetings relevant to this one
- 2-3 suggested talking points or questions the person should be ready for
- Any cross-meeting patterns or connections worth flagging

Guidelines:
- Be specific and direct. No filler phrases ("It's important to note that...")
- Ground every claim in the provided context. Do not speculate beyond it
- If there is no relevant history, say so briefly rather than padding the brief
- Write in plain English suitable for a busy professional skimming before a call

Return a single plain-text brief. No JSON. No headers unless they genuinely aid scannability."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


class _Model(StrEnum):
    EXTRACTION = "claude-sonnet-4-6"
    BRIEF = "claude-opus-4-6"
    MERGE = "claude-sonnet-4-6"
    DIGEST = "claude-sonnet-4-6"


def _instructor_client() -> instructor.Instructor:
    return instructor.from_anthropic(anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY))


def _raw_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)


def _openai_client() -> openai.OpenAI:
    return openai.OpenAI(api_key=settings.OPENAI_API_KEY)


def _extract[T](
    system_prompt: str,
    transcript: str,
    response_model: type[T],
    model: _Model = _Model.EXTRACTION,
) -> T:
    """Run a structured extraction call via instructor. Transcript content is not logged."""
    logger.debug("LLM extraction call — model=%s response_model=%s", model, response_model.__name__)
    result: T = _instructor_client().messages.create(  # type: ignore[type-var]
        model=str(model),
        max_tokens=2048,
        system=system_prompt,
        messages=[{"role": "user", "content": f"Here is the meeting transcript:\n\n{transcript}"}],
        response_model=response_model,
    )
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def extract_topics(transcript: str) -> TopicList:
    """Extract discussion topics from a transcript.

    Returns:
        TopicList with validated Topic objects, each linked to source quotes.
    """
    return _extract(_TOPIC_SYSTEM_PROMPT, transcript, TopicList)


def extract_commitments(transcript: str) -> CommitmentList:
    """Extract commitments and action items from a transcript.

    Returns:
        CommitmentList with validated Commitment objects (owner, due_date, status).
    """
    return _extract(_COMMITMENT_SYSTEM_PROMPT, transcript, CommitmentList)


def extract_entities(transcript: str) -> EntityList:
    """Extract named entities from a transcript.

    Returns:
        EntityList with validated Entity objects (name, type, mention count).
    """
    return _extract(_ENTITY_SYSTEM_PROMPT, transcript, EntityList)


def check_topic_merge(label_a: str, summary_a: str, label_b: str, summary_b: str) -> bool:
    """Return True when two topics represent the same underlying initiative."""
    prompt = f"""Two topics were extracted from different meetings for the same user.

Topic A label: "{label_a}"
Topic A summary: "{summary_a}"

Topic B label: "{label_b}"
Topic B summary: "{summary_b}"

Do these represent the same concrete ongoing initiative or discussion thread across meetings?
Answer YES only when both topics clearly refer to the same workstream, project, or repeated thread.
Answer NO when they are merely adjacent, broadly related, or share one generic idea/word such as tracking, strategy, planning, education, marketing, content, or reporting.
If one is a subtopic, analogy, example, or different operational problem inside the same business area, answer NO.
Answer only YES or NO."""

    logger.debug("LLM merge check — model=%s", _Model.MERGE)
    response = _raw_client().messages.create(
        model=str(_Model.MERGE),
        max_tokens=8,
        messages=[{"role": "user", "content": prompt}],
    )
    block = response.content[0]
    if not isinstance(block, TextBlock):
        raise ValueError(f"Expected TextBlock from merge check, got {type(block).__name__}")
    return block.text.strip().upper() == "YES"


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Generate embeddings for a list of texts using OpenAI text-embedding-3-small.

    Args:
        texts: List of strings to embed. Transcript content is not logged.

    Returns:
        List of embedding vectors (each is a list of 1536 floats), in the same
        order as the input texts.

    Raises:
        ValueError: If texts is empty.
    """
    if not texts:
        raise ValueError("texts must be non-empty")

    logger.debug("Embedding %d texts", len(texts))
    response = _openai_client().embeddings.create(
        model=_EMBEDDING_MODEL,
        input=texts,
        dimensions=_EMBEDDING_DIMENSIONS,
    )
    # API guarantees order matches input — sort by index to be safe
    ordered = sorted(response.data, key=lambda d: d.index)
    return [item.embedding for item in ordered]


def generate_meeting_digest(
    topics: list[dict[str, str]],
    commitments: list[dict[str, str | None]],
    entities: list[dict[str, str]],
) -> str:
    """Generate a plain-text digest of a meeting from its extracted intelligence.

    Called once at ingest time after extraction is complete. The digest is stored
    on conversations.digest and embedded for semantic search. It is never regenerated.

    Args:
        topics: List of dicts with 'label' and 'summary' keys.
        commitments: List of dicts with 'text', 'owner', and optional 'due_date' keys.
        entities: List of dicts with 'name' and 'type' keys.

    Returns:
        Plain-text 3-5 sentence digest string.

    Note:
        Input data is single-user scoped and must never be logged.
    """
    if not topics and not commitments and not entities:
        return ""

    # Build a structured context string — never log this
    parts: list[str] = []
    if topics:
        topic_lines = "\n".join(f"- {t['label']}: {t.get('summary', '')}" for t in topics)
        parts.append(f"Topics discussed:\n{topic_lines}")
    if commitments:
        commitment_lines = "\n".join(
            f"- {c['owner']} committed to: {c['text']}"
            + (f" (by {c['due_date']})" if c.get("due_date") else "")
            for c in commitments
        )
        parts.append(f"Commitments made:\n{commitment_lines}")
    if entities:
        entity_lines = ", ".join(f"{e['name']} ({e['type']})" for e in entities)
        parts.append(f"People and projects mentioned: {entity_lines}")

    context = "\n\n".join(parts)

    logger.debug("LLM call — generating meeting digest model=%s", _Model.DIGEST)
    response = _raw_client().messages.create(
        model=str(_Model.DIGEST),
        max_tokens=256,
        system=_DIGEST_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": context}],
    )
    block = response.content[0]
    if not isinstance(block, TextBlock):
        raise ValueError(f"Expected TextBlock from digest generation, got {type(block).__name__}")
    return block.text.strip()


class CitationRef(BaseModel):
    result_id: str
    result_type: str
    conversation_id: str
    conversation_title: str
    meeting_date: str
    snippet: str


class AnswerResult(BaseModel):
    answer: str
    citations: list[CitationRef]


_ANSWER_SYSTEM_PROMPT = """You are a personal meeting intelligence assistant.
The user has asked a question about their past meetings.
You have been given a set of relevant excerpts retrieved from their meeting history.
Answer concisely and directly based only on the provided excerpts.
Do not speculate beyond what the excerpts contain.
For each claim you make, cite the source excerpt by its index number [1], [2], etc.
If the excerpts do not contain enough information to answer the question, say so clearly.
Return cited_indices as a list of the [N] numbers from the context that support your answer.
For example, if your answer draws on sources [1] and [3], return cited_indices: [1, 3]."""


class _InstructorAnswer(BaseModel):
    """Private intermediate model: Claude returns index numbers, server resolves to CitationRef."""

    answer: str
    cited_indices: list[int]  # 1-based indices matching [N] labels in the context block


def answer_question(
    question: str,
    context_results: list[dict[str, Any]],
) -> AnswerResult:
    """Synthesise an answer to a user question from retrieved meeting context.

    Args:
        question: The user's natural language question. Never logged.
        context_results: Top-K search results as dicts (result_id, result_type, title,
            text, conversation_id, conversation_title, meeting_date, score).

    Returns:
        AnswerResult with answer text and citation references.

    Note:
        Input context contains meeting content and must never be logged.
    """
    if not context_results:
        return AnswerResult(
            answer="I don't have enough context from your meetings to answer that question.",
            citations=[],
        )

    # Build numbered context block — never log this
    context_lines: list[str] = []
    for i, ctx in enumerate(context_results, 1):
        title = ctx.get("title", "")
        text = ctx.get("text", "")
        conv_title = ctx.get("conversation_title", "")
        meeting_date = ctx.get("meeting_date", "")
        context_lines.append(
            f"[{i}] Source: {conv_title} ({meeting_date})\n"
            f"    Topic/Entity: {title}\n"
            f"    Content: {text}"
        )
    context_block = "\n\n".join(context_lines)

    logger.debug(
        "LLM call — answer_question model=%s context_items=%d", _Model.DIGEST, len(context_results)
    )
    # Claude returns only index numbers — server resolves them to CitationRef objects.
    # This avoids asking Claude to populate database UUIDs it cannot know.
    instructor_result: _InstructorAnswer = _instructor_client().messages.create(
        model=str(_Model.DIGEST),
        max_tokens=1024,
        system=_ANSWER_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": f"Question: {question}\n\nContext:\n{context_block}",
            }
        ],
        response_model=_InstructorAnswer,
    )

    # Map cited indices → CitationRef using the actual context_results metadata
    citations: list[CitationRef] = []
    for idx in instructor_result.cited_indices:
        if 1 <= idx <= len(context_results):
            src = context_results[idx - 1]
            citations.append(
                CitationRef(
                    result_id=str(src.get("result_id", "")),
                    result_type=str(src.get("result_type", "")),
                    conversation_id=str(src.get("conversation_id", "")),
                    conversation_title=str(src.get("conversation_title", "")),
                    meeting_date=str(src.get("meeting_date", "")),
                    snippet=str(src.get("text", ""))[:200],
                )
            )

    return AnswerResult(answer=instructor_result.answer, citations=citations)


def generate_brief(context: str) -> str:
    """Generate a pre-meeting brief from context text.

    Args:
        context: Structured context string (topics, commitments, connections, calendar event).

    Returns:
        Plain-text brief as a single string.
    """
    logger.debug("LLM call — generating brief model=%s", _Model.BRIEF)
    response = _raw_client().messages.create(
        model=str(_Model.BRIEF),
        max_tokens=1024,
        system=_BRIEF_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": context}],
    )
    block = response.content[0]
    if not isinstance(block, TextBlock):
        raise ValueError(f"Expected TextBlock from brief generation, got {type(block).__name__}")
    return block.text
