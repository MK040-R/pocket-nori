import json
import os

import anthropic

from models import CommitmentExtraction, EntityList, TopicList
from prompts import (
    COMMITMENT_SYSTEM_PROMPT,
    ENTITY_SYSTEM_PROMPT,
    TOPIC_SYSTEM_PROMPT,
)

MODEL = os.getenv("LLM_MODEL", "claude-opus-4-6")


def _get_client() -> anthropic.Anthropic:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "ANTHROPIC_API_KEY environment variable is not set. "
            "Copy .env.example to .env and add your key."
        )
    return anthropic.Anthropic(api_key=api_key)


def _call_llm(system_prompt: str, transcript: str) -> str:
    client = _get_client()
    message = client.messages.create(
        model=MODEL,
        max_tokens=2048,
        system=system_prompt,
        messages=[
            {
                "role": "user",
                "content": f"Here is the meeting transcript:\n\n{transcript}",
            }
        ],
    )
    return message.content[0].text


def extract_topics(transcript: str) -> TopicList:
    raw = _call_llm(TOPIC_SYSTEM_PROMPT, transcript)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"LLM returned non-JSON response for topic extraction: {raw[:200]}"
        ) from exc
    return TopicList.model_validate(data)


def extract_commitments(transcript: str) -> CommitmentExtraction:
    raw = _call_llm(COMMITMENT_SYSTEM_PROMPT, transcript)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"LLM returned non-JSON response for commitment extraction: {raw[:200]}"
        ) from exc
    return CommitmentExtraction.model_validate(data)


def extract_entities(transcript: str) -> EntityList:
    raw = _call_llm(ENTITY_SYSTEM_PROMPT, transcript)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"LLM returned non-JSON response for entity extraction: {raw[:200]}"
        ) from exc
    return EntityList.model_validate(data)
