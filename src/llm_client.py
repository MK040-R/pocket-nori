"""
LLM gateway — ALL Claude API calls must go through this module.

Rules enforced here:
- Transcript content is never logged.
- Extraction uses claude-sonnet-4-6; briefs use claude-opus-4-6.
- JSON parsing errors raise ValueError with truncated (safe) context only.
"""

import json
import logging
from enum import StrEnum

import anthropic

from src.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompts (sourced from spikes/spike3_llm_extraction/prompts.py)
# ---------------------------------------------------------------------------

_TOPIC_SYSTEM_PROMPT = """You are an expert meeting analyst. Your task is to extract the main discussion topics from a meeting transcript.

For each topic:
- Provide a short, descriptive label (3-50 characters)
- Write a 1-2 sentence summary of what was discussed
- Determine if the topic is "open" (unresolved, needs follow-up) or "resolved" (concluded, decided)
- Include up to 2 verbatim quotes that best represent the topic

Guidelines:
- Extract only topics that are clearly discussed in the transcript — do not invent or infer topics not present
- Prefer specificity over generality (e.g., "Q3 hiring plan" not "hiring")
- A topic should represent a coherent subject of discussion, not a single passing remark
- Accuracy over quantity: 3 real topics is better than 8 vague ones
- If participants returned to a subject multiple times, treat it as one topic

Return your response as a JSON object matching this schema exactly:
{
  "topics": [
    {
      "label": "string (short topic name)",
      "summary": "string (1-2 sentences)",
      "status": "open | resolved",
      "key_quotes": ["string", "string"]
    }
  ]
}

Return only the JSON object. No explanation or preamble."""

_COMMITMENT_SYSTEM_PROMPT = """You are an expert meeting analyst. Your task is to extract commitments and action items from a meeting transcript.

A commitment is a statement where a named participant agrees to do something. This includes:
- Explicit action items ("I'll send the report by Friday")
- Agreements to follow up ("Let me check on that and get back to you")
- Assigned tasks ("Can you own the API integration? — Sure, I'll handle it")

For each commitment:
- Capture the exact text or a close paraphrase of what was committed
- Identify the person who owns the commitment (use their name as spoken in the transcript)
- Extract a due date if one was explicitly mentioned (ISO format: YYYY-MM-DD); leave null if not stated
- Set status to "open" unless the transcript explicitly confirms the commitment was completed

Guidelines:
- Only extract commitments with a clear owner — do not include vague "we should" statements with no named owner
- Do not fabricate due dates; only include them if stated in the transcript
- Accuracy over quantity: a few real commitments is better than many uncertain ones

Return your response as a JSON object matching this schema exactly:
{
  "commitments": [
    {
      "text": "string",
      "owner": "string (person's name)",
      "due_date": "YYYY-MM-DD or null",
      "status": "open | resolved"
    }
  ]
}

Return only the JSON object. No explanation or preamble."""

_ENTITY_SYSTEM_PROMPT = """You are an expert meeting analyst. Your task is to extract named entities from a meeting transcript.

Extract entities of these types only:
- person: named individuals mentioned or speaking in the transcript
- project: named projects, initiatives, or workstreams
- company: organizations, companies, or teams (other than the speakers' own company, unless named)
- product: named software products, tools, platforms, or features

For each entity:
- Use the name exactly as it appears most completely in the transcript
- Classify it as one of: person, project, company, or product
- Count the total number of times it is mentioned (approximate is fine)

Guidelines:
- Only extract entities with proper names — do not include generic references ("the backend", "the client")
- If a person is referred to by first name only and it is unambiguous, use that name
- If the same entity is referred to by multiple names, count them together under the canonical name
- Accuracy over quantity

Return your response as a JSON object matching this schema exactly:
{
  "entities": [
    {
      "name": "string",
      "type": "person | project | company | product",
      "mentions": integer
    }
  ]
}

Return only the JSON object. No explanation or preamble."""

_BRIEF_SYSTEM_PROMPT = """You are an expert meeting strategist. Given context about a person's past meetings and an upcoming calendar event, write a concise pre-meeting brief.

The brief should include:
- A 2-3 sentence situational summary: what relevant history exists with these people or topics
- Open commitments from previous meetings that are relevant to this meeting
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


def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)


def _call(system_prompt: str, user_content: str, model: _Model, max_tokens: int = 2048) -> str:
    """Make a single Claude API call. Transcript content is not logged."""
    logger.debug("LLM call — model=%s max_tokens=%d", model, max_tokens)
    response = _client().messages.create(
        model=str(model),
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_content}],
    )
    return response.content[0].text


def _parse_json(raw: str, task_name: str) -> dict:
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        # Truncate to avoid leaking transcript content in error messages
        preview = raw[:120].replace("\n", " ")
        raise ValueError(f"LLM returned non-JSON for {task_name}. Preview: {preview!r}") from exc


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def extract_topics(transcript: str) -> dict:
    """Extract discussion topics from a transcript.

    Returns:
        dict with key "topics" — list of {label, summary, status, key_quotes}.
    """
    raw = _call(
        _TOPIC_SYSTEM_PROMPT, f"Here is the meeting transcript:\n\n{transcript}", _Model.EXTRACTION
    )
    return _parse_json(raw, "topic extraction")


def extract_commitments(transcript: str) -> dict:
    """Extract commitments and action items from a transcript.

    Returns:
        dict with key "commitments" — list of {text, owner, due_date, status}.
    """
    raw = _call(
        _COMMITMENT_SYSTEM_PROMPT,
        f"Here is the meeting transcript:\n\n{transcript}",
        _Model.EXTRACTION,
    )
    return _parse_json(raw, "commitment extraction")


def extract_entities(transcript: str) -> dict:
    """Extract named entities from a transcript.

    Returns:
        dict with key "entities" — list of {name, type, mentions}.
    """
    raw = _call(
        _ENTITY_SYSTEM_PROMPT, f"Here is the meeting transcript:\n\n{transcript}", _Model.EXTRACTION
    )
    return _parse_json(raw, "entity extraction")


def generate_brief(context: str) -> str:
    """Generate a pre-meeting brief from context text.

    Args:
        context: Structured context string (topics, commitments, connections, calendar event).

    Returns:
        Plain-text brief as a single string.
    """
    logger.debug("LLM call — generating brief")
    return _call(_BRIEF_SYSTEM_PROMPT, context, _Model.BRIEF, max_tokens=1024)
