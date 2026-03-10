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
from pydantic import BaseModel, Field

from src.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Extraction response models
# ---------------------------------------------------------------------------


class TopicResult(BaseModel):
    label: str = Field(description="Short topic name, 3-50 characters")
    summary: str = Field(description="1-2 sentence summary of what was discussed")
    status: Literal["open", "resolved"]
    key_quotes: list[str] = Field(default_factory=list, max_length=2)


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

_TOPIC_SYSTEM_PROMPT = """You are an expert meeting analyst. Extract the main discussion topics from a meeting transcript.

For each topic:
- Provide a short, descriptive label (3-50 characters)
- Write a 1-2 sentence summary of what was discussed
- Determine if the topic is "open" (unresolved, needs follow-up) or "resolved" (concluded, decided)
- Include up to 2 verbatim quotes that best represent the topic

Guidelines:
- Extract only topics clearly discussed — do not invent or infer topics not present
- Prefer specificity over generality (e.g., "Q3 hiring plan" not "hiring")
- A topic should represent a coherent subject of discussion, not a single passing remark
- Accuracy over quantity: 3 real topics is better than 8 vague ones
- If participants returned to a subject multiple times, treat it as one topic"""

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


def _instructor_client() -> instructor.Instructor:
    return instructor.from_anthropic(anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY))


def _raw_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)


def _extract(
    system_prompt: str, transcript: str, response_model: type, model: _Model = _Model.EXTRACTION
):
    """Run a structured extraction call via instructor. Transcript content is not logged."""
    logger.debug("LLM extraction call — model=%s response_model=%s", model, response_model.__name__)
    return _instructor_client().messages.create(
        model=str(model),
        max_tokens=2048,
        system=system_prompt,
        messages=[{"role": "user", "content": f"Here is the meeting transcript:\n\n{transcript}"}],
        response_model=response_model,
    )


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
    return response.content[0].text
