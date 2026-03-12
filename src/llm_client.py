"""
LLM gateway — ALL Claude API calls must go through this module.

Rules enforced here:
- Transcript content is never logged.
- Extraction uses claude-sonnet-4-6; briefs use claude-opus-4-6.
- All extraction returns validated Pydantic objects via instructor — no raw JSON parsing.
"""

import logging
from enum import StrEnum
from typing import Literal

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
