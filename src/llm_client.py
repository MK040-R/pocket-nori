"""
LLM gateway — ALL Claude API calls must go through this module.

Rules enforced here:
- Transcript content is never logged.
- Extraction uses claude-sonnet-4-6; briefs use claude-opus-4-6.
- All extraction returns validated Pydantic objects via instructor — no raw JSON parsing.
"""

import logging
from collections.abc import Generator
from enum import StrEnum
from typing import Any, Literal

import anthropic
import instructor
import openai
from anthropic.types import MessageParam, TextBlock
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
    action_type: Literal["commitment", "follow_up"] = Field(
        default="commitment",
        description=(
            "commitment = the meeting participant personally owes this action; "
            "follow_up = the participant is tracking an action they expect FROM someone else"
        ),
    )


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

_COMMITMENT_SYSTEM_PROMPT = """You are an expert meeting analyst. Extract all actions and follow-ups from a meeting transcript.

There are two types of actions:
- commitment: a participant personally agrees to do something ("I'll send the report by Friday", "I'll own the API integration")
- follow_up: a participant expects an action FROM someone else and is tracking it ("Can you send me the contract?", "We're waiting on Legal to review this")

For each action:
- Capture the exact text or a close paraphrase
- Identify the person who owns it (use their name as spoken)
- Extract a due date only if explicitly mentioned (ISO format YYYY-MM-DD); leave null if not stated
- Set status to "open" unless the transcript explicitly confirms completion
- Set action_type to "commitment" if the owner is doing the work themselves, or "follow_up" if the owner is waiting on/tracking someone else

Guidelines:
- Only extract actions with a clear owner — exclude vague "we should" statements
- Exclude observations, summaries, decisions, and status updates that are not forward-looking actions
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

_HOME_SUMMARY_SYSTEM_PROMPT = """You are a personal meeting intelligence assistant.
Given a brief context about a person's day - upcoming meetings, open actions, and recent discussion topics - write a 2-3 sentence plain-English briefing for them.

Guidelines:
- Write in second person ("You have...", "Your recent meetings covered...").
- Be specific: use the actual meeting names, counts, and topic names provided.
- Do not speculate beyond the data given.
- If context is sparse, write something grounding and brief — never pad.
- Plain prose only. No headers, no bullet points, no JSON."""

_DRAFT_EMAIL_SYSTEM_PROMPT = """You are a professional writing assistant. Given a commitment or follow-up from a meeting, draft a concise email to action it.

You will receive:
- The commitment/follow-up text
- The meeting context (title, date, relevant transcript excerpts)
- The format requested (email or message)

For email format:
- Write a clear subject line (10 words max)
- Write a professional but concise body (3-8 sentences)
- Reference the meeting naturally ("Following up from our meeting on...")
- End with a clear ask or next step

For message format (Slack/Teams style):
- Skip the subject line (return empty string for subject)
- Write 2-4 casual but clear sentences
- Get straight to the point

Guidelines:
- Be specific — reference actual details from the transcript context
- Do not pad or use filler phrases
- Suggest a recipient based on the commitment owner field
- Never include raw IDs or internal metadata"""

_CHAT_SYSTEM_PROMPT = """You are Pocket Nori — a personal meeting intelligence assistant.
The user is asking questions about their past meetings, topics, commitments, and connections.
You have been given relevant excerpts retrieved from their meeting history as context.

Guidelines:
- Answer directly and concisely based on the provided context.
- For each claim, cite the source by referencing the meeting title and date in parentheses.
- If the context doesn't contain the answer, say so clearly — don't speculate.
- Be conversational but professional. Use "you" to address the user.
- Keep responses focused: aim for 2-5 sentences unless the question demands a longer answer.
- Never reveal raw database IDs or internal metadata — only human-readable information."""

_CATEGORY_SYSTEM_PROMPT = """Classify this meeting into exactly one category based on the title, topics discussed, and participants.

Categories:
- strategy: high-level planning, roadmap, vision, or goal-setting discussions
- client: external client meetings, demos, presentations, or negotiations
- 1on1: one-on-one meetings between two people (manager/report, peer check-in)
- agency: meetings with external agencies, contractors, or vendors
- partner: partner or partnership discussions
- team: internal team meetings, standups, retrospectives, all-hands
- other: anything that doesn't fit the above categories

Return ONLY the category name, nothing else."""


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


def stream_chat_response(
    conversation_history: list[dict[str, str]],
    context_results: list[dict[str, Any]],
    user_message: str,
) -> Generator[str]:
    """Stream a chat response given conversation history and retrieved context.

    Args:
        conversation_history: Previous messages as [{"role": "user"|"assistant", "content": "..."}].
        context_results: Top-K search results as dicts (same shape as answer_question).
        user_message: The current user question. Never logged.

    Yields:
        Text chunks as they arrive from the Claude streaming API.

    Note:
        All input content is user-scoped and must never be logged.
    """
    # Build context block from retrieved results
    context_block = ""
    if context_results:
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
        context_block = "\n\nRelevant context from the user's meeting history:\n\n" + "\n\n".join(
            context_lines
        )

    # Build messages: history + current user message with context
    messages: list[MessageParam] = []
    for msg in conversation_history:
        messages.append({"role": msg["role"], "content": msg["content"]})  # type: ignore[typeddict-item]

    current_content = user_message
    if context_block:
        current_content = f"{user_message}{context_block}"
    messages.append({"role": "user", "content": current_content})

    logger.debug(
        "LLM call — stream_chat_response model=%s history_len=%d context_items=%d",
        _Model.EXTRACTION,
        len(conversation_history),
        len(context_results),
    )

    with _raw_client().messages.stream(
        model=str(_Model.EXTRACTION),
        max_tokens=1024,
        system=_CHAT_SYSTEM_PROMPT,
        messages=messages,
    ) as stream:
        for text in stream.text_stream:
            yield text


def generate_chat_title(first_message: str) -> str:
    """Generate a short title for a chat session from the first user message.

    Args:
        first_message: The user's first question. Never logged.

    Returns:
        A short title string (3-8 words).
    """
    logger.debug("LLM call — generate_chat_title model=%s", _Model.EXTRACTION)
    response = _raw_client().messages.create(
        model=str(_Model.EXTRACTION),
        max_tokens=30,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Generate a short title (3-8 words, no quotes) for a chat that starts with "
                    f"this question: {first_message}"
                ),
            }
        ],
    )
    block = response.content[0]
    if not isinstance(block, TextBlock):
        return "New chat"
    return block.text.strip().strip('"').strip("'")[:80]


class DraftResult(BaseModel):
    subject: str
    body: str
    recipient_suggestion: str


def generate_commitment_draft(
    commitment_text: str,
    owner: str,
    meeting_title: str,
    meeting_date: str,
    transcript_context: str,
    format: Literal["email", "message"] = "email",
) -> DraftResult:
    """Generate a draft email or message from a commitment and its context.

    Args:
        commitment_text: The commitment or follow-up text.
        owner: Who owns the commitment (used for recipient suggestion).
        meeting_title: Title of the source meeting.
        meeting_date: Date of the source meeting.
        transcript_context: Relevant transcript excerpts. Never logged.
        format: "email" or "message".

    Returns:
        DraftResult with subject, body, and recipient_suggestion.
    """
    parts: list[str] = [
        f"Commitment: {commitment_text}",
        f"Owner/Assigned to: {owner}",
        f"Meeting: {meeting_title} ({meeting_date})",
        f"Format: {format}",
    ]
    if transcript_context:
        parts.append(f"Relevant transcript context:\n{transcript_context}")

    user_content = "\n\n".join(parts)

    logger.debug(
        "LLM call — generate_commitment_draft model=%s format=%s", _Model.EXTRACTION, format
    )
    result: DraftResult = _instructor_client().messages.create(
        model=str(_Model.EXTRACTION),
        max_tokens=512,
        system=_DRAFT_EMAIL_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
        response_model=DraftResult,
    )
    return result


def classify_meeting_category(
    title: str,
    topic_labels: list[str],
    entity_names: list[str],
) -> str | None:
    """Classify a meeting into one of the predefined categories.

    Args:
        title: Meeting title.
        topic_labels: Up to 5 extracted topic labels.
        entity_names: Up to 5 extracted entity names.

    Returns:
        One of: strategy, client, 1on1, agency, partner, team, other.
        Returns None if classification fails.
    """
    parts: list[str] = [f"Meeting title: {title}"]
    if topic_labels:
        parts.append(f"Topics discussed: {', '.join(topic_labels[:5])}")
    if entity_names:
        parts.append(f"Participants/entities: {', '.join(entity_names[:5])}")
    context = "\n".join(parts)

    valid_categories = {"strategy", "client", "1on1", "agency", "partner", "team", "other"}

    logger.debug("LLM call — classify_meeting_category model=%s", _Model.EXTRACTION)
    try:
        response = _raw_client().messages.create(
            model=str(_Model.EXTRACTION),
            max_tokens=10,
            system=_CATEGORY_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": context}],
        )
        block = response.content[0]
        if not isinstance(block, TextBlock):
            return None
        result = block.text.strip().lower()
        return result if result in valid_categories else None
    except Exception as exc:
        logger.warning("Meeting category classification failed: %s", type(exc).__name__)
        return None


def generate_home_summary(
    upcoming_meeting_titles: list[str],
    open_commitment_count: int,
    recent_topic_labels: list[str],
) -> str:
    """Generate a 2-3 sentence personalized daily briefing for the home page.

    Args:
        upcoming_meeting_titles: Titles of meetings starting later today (max 3).
        open_commitment_count: Total number of open actions for this user.
        recent_topic_labels: Most recent distinct topic labels (max 3).

    Returns:
        Plain-text 2-3 sentence summary. Never logged — may reference user data.
    """
    parts: list[str] = []
    if upcoming_meeting_titles:
        mtg_list = ", ".join(f'"{t}"' for t in upcoming_meeting_titles)
        parts.append(f"Upcoming meetings today: {mtg_list}.")
    else:
        parts.append("No upcoming meetings scheduled for the rest of today.")
    parts.append(f"Open actions: {open_commitment_count}.")
    if recent_topic_labels:
        parts.append(f"Recent discussion topics: {', '.join(recent_topic_labels)}.")

    context = "\n".join(parts)
    logger.debug("LLM call — generate_home_summary model=%s", _Model.EXTRACTION)
    response = _raw_client().messages.create(
        model=str(_Model.EXTRACTION),
        max_tokens=200,
        system=_HOME_SUMMARY_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": context}],
    )
    block = response.content[0]
    if not isinstance(block, TextBlock):
        raise ValueError(f"Expected TextBlock from home summary, got {type(block).__name__}")
    return block.text.strip()
