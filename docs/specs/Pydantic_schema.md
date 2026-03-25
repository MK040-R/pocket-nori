# Pocket Nori — Pydantic Schema (Complete)

**Date:** March 24, 2026  
**Context:** These schemas define the data structures across all 5 stages of the topic intelligence pipeline.

---

## Stage 1: Segmentation Output

```python
class DiscussionBlock(BaseModel):
    block_id: int
    start_index: int                    # First utterance index in transcript
    end_index: int                      # Last utterance index
    start_timestamp: float | None       # Seconds from meeting start
    end_timestamp: float | None
    shift_type: str                     # "explicit_transition" | "silence_gap" | "speaker_shift" | "end_of_meeting"
    participants: list[str]             # Speakers who talked in this block
    duration_seconds: float
    utterance_count: int
    text: str                           # Concatenated text of all utterances in block
```

---

## Stage 2: Entity Extraction Output

```python
class Entity(BaseModel):
    type: str              # "person" | "company" | "product" | "date" | "deadline" | "monetary_value" | "artifact" | "project_code"
    value: str             # Normalized value (e.g., "Rahul Sharma", "Acme Corp", "March 15")
    raw: str               # Original text as spoken (e.g., "Rahul", "the Acme guys", "next Friday")
    confidence: float      # spaCy confidence score (0.0–1.0)
```

---

## Stage 3: Meeting Context (Pre-computed, No LLM)

```python
class MeetingContext(BaseModel):
    title: str                          # Calendar event title
    categories: list[str]               # ["strategy", "standup", "external", etc.] — from title keyword lookup
    extraction_hints: list[str]         # Human-readable hints injected into LLM prompt
    has_executive: bool                 # Whether any participant has executive-level role
    participant_count: int
    participants: list[str]             # Names from calendar
    participant_roles: dict[str, str]   # {"Rahul": "ic", "Sarah": "manager", "CEO Name": "executive"}
    recurring_series: str | None        # Series name if recurring, null if ad-hoc
```

---

## Stage 3 Tier 1: Candidacy Score (No LLM)

```python
class BlockCandidacy(BaseModel):
    block_id: int
    candidacy_score: float              # 0.0–1.0, computed from deterministic signals
    is_candidate: bool                  # score >= 0.3
    signals: dict                       # Breakdown of what contributed to the score
    # Example signals dict:
    # {
    #     "entity_density": 0.3,
    #     "multi_speaker": 0.25,
    #     "adjective_signals": ["urgent", "deadline"],
    #     "adjective_score": 0.2,
    #     "decision_language": True,
    #     "decision_score": 0.2,
    #     "keyphrases": ["Q3 pricing", "tiered model"],
    #     "keyphrase_score": 0.15,
    #     "executive_speaker": False,
    #     "executive_score": 0.0
    # }
```

---

## Stage 3 Tier 2: Candidate Topic (LLM Output — Haiku)

This is the core extraction schema. Haiku returns this for each candidate block.

```python
class CandidateTopic(BaseModel):
    # Validation
    is_valid_topic: bool
    skip_reason: str | None             # "personal" | "check_in" | "logistics" | "no_substance" | null

    # Topic identity
    name: str | None                    # Verb+noun format: "Finalizing Q3 pricing model"
    type: str | None                    # "discussion" | "decision" | "status_update" | "brainstorm" | "action_planning"

    # Content
    key_points: list[str]               # Max 3 substantive points
    decision_made: str | None           # What was decided, if anything. null if no decision.
    commitments: list[Commitment] | None
    open_questions: list[str]           # Unresolved items

    # Matching signals (critical for Stage 5 resolution)
    related_keywords: list[str]         # Alternate phrasings, abbreviations, codenames
    entities: list[Entity]              # Confirmed/corrected from Stage 2 + any LLM additions

    # Priority and context
    adjective_signals: list[str]        # Qualifiers found in speech: "urgent", "blocking", "client ask"
    priority_level: str                 # "critical" | "high" | "normal" | "low"
    source_context: str | None          # "client_request" | "leadership_directive" | "internal" | "compliance" | null
    speaker_seniority: str | None       # "executive" | "manager" | "ic" | null

    # Metadata
    discussion_block_id: int            # Links to Stage 1 output
    meeting_title_mapping: str | None   # "primary" | "tangential" | null
    confidence_score: float             # 0.0–1.0
    segment_ids: list[str]              # Source transcript utterance references


class Commitment(BaseModel):
    owner: str                          # Person who committed
    action: str                         # What they committed to do
    deadline: str | None                # "by Friday", "end of Q3", null if unspecified


class MeetingExtraction(BaseModel):
    meeting_id: str
    meeting_context: MeetingContext
    blocks: list[DiscussionBlock]       # From Stage 1
    topics: list[CandidateTopic]        # From Stage 3 Tier 2
    skipped_blocks: int                 # Blocks that didn't pass Tier 1
    total_blocks: int
```

---

## Stage 5: Resolution Output

```python
class ResolutionDecision(BaseModel):
    new_topic_name: str                 # The candidate topic being resolved
    candidate_id: str | None            # Existing topic it matched against (null if new)
    relationship: str                   # "same" | "related" | "derived_from" | "unrelated" | "new"
    confidence: float                   # 0.0–1.0
    reasoning: str                      # One-sentence explanation
    method: str                         # "auto_high_confidence" | "auto_low_confidence" | "llm_resolution"


class MergeCandidate(BaseModel):
    existing_topic_id: str
    existing_topic_label: str
    combined_score: float               # 0.0–1.0
    score_breakdown: dict               # {"semantic": 0.8, "keyword": 0.6, "entity": 0.9, "participant": 0.5}
    aliases: list[str]
    last_mentioned_at: str              # ISO datetime
    participant_names: list[str]
    entities: list[Entity]
```

---

## Graph Entities (What Gets Stored)

```python
class TopicNode(BaseModel):
    id: str                             # UUID
    label: str                          # Canonical name (verb+noun format)
    aliases: list[str]                  # All alternate names accumulated over time
    type: str                           # Most recent type: "discussion" | "decision" | etc.
    status: str                         # "active" | "resolved" | "stale"
    priority_level: str                 # Highest priority ever assigned
    source_context: str | None          # Most recent source context
    speaker_seniority: str | None       # Highest seniority speaker who engaged

    # Accumulated content
    entities: list[Entity]              # All entities ever associated with this topic
    all_keywords: list[str]             # Union of related_keywords from all mentions
    decisions: list[str]                # All decisions made across the arc
    open_questions: list[str]           # Currently unresolved questions
    commitments: list[Commitment]       # Active commitments

    # Temporal
    first_mentioned_at: str             # ISO datetime
    last_mentioned_at: str              # ISO datetime
    mention_count: int                  # Number of meetings where this topic appeared
    conversation_ids: list[str]         # All meetings/conversations linked to this topic

    # Graph relationships
    related_topic_ids: list[str]        # "related" links
    derived_from_id: str | None         # Parent topic if this was forked
    derived_topics: list[str]           # Child topics forked from this one

    # Embedding
    embedding: list[float]              # Re-computed on merge (label + all aliases + all keywords)

    # Metadata
    created_at: str
    updated_at: str
    user_id: str
```

---

## Notes

- **Entity extraction (Stage 2) is deterministic.** spaCy NER + regex patterns. Same input → same output.
- **Tier 1 candidacy scoring is deterministic.** Same input → same score → same candidate set.
- **Tier 2 (Haiku) and Stage 5 (Sonnet) are the only LLM-dependent stages.** Variance is absorbed by alias accumulation and keyword matching in the resolution layer.
- **Temperature = 0** for all LLM calls.
- **`instructor` library** enforces schema compliance — LLM output must conform to these Pydantic models or the call fails and retries.
