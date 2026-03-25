# Pocket Nori — Topic Intelligence: Definitive Specification

**Date:** March 24, 2026  
**Status:** Final. This document supersedes all previous topic intelligence docs.  
**Design principles:** Cost-efficient (target $0.05–0.20 per meeting for extraction pipeline), deterministic where possible (minimize LLM dependence), accurate (>90% topic extraction precision target).

---

## 1. Pipeline Overview

```
Recall.ai                    Your Pipeline
─────────                    ─────────────
Audio capture     ──→  Transcript + speaker labels + timestamps
                              │
                              ▼
                     ┌─ Stage 1: SEGMENTATION (no LLM) ─────────────┐
                     │  Heuristic block detection                    │
                     │  + calendar metadata injection                │
                     └───────────────────────────────────────────────┘
                              │
                              ▼
                     ┌─ Stage 2: ENTITY EXTRACTION (no LLM) ────────┐
                     │  spaCy NER + keyword dictionary               │
                     │  People, companies, products, dates, deadlines│
                     └───────────────────────────────────────────────┘
                              │
                              ▼
                     ┌─ Stage 3: CANDIDATE TOPIC IDENTIFICATION ────┐
                     │  Tier 1: Non-LLM signals (cheap, fast)       │
                     │  Tier 2: LLM validation (targeted, only      │
                     │          on candidates from Tier 1)           │
                     └───────────────────────────────────────────────┘
                              │
                              ▼
                     ┌─ Stage 4: FILTERING ─────────────────────────┐
                     │  Work vs. personal classification             │
                     │  Check-in exclusion                           │
                     │  Seniority-based promotion                    │
                     │  Qualification criteria gate                  │
                     └───────────────────────────────────────────────┘
                              │
                              ▼
                     ┌─ Stage 5: RESOLUTION (LLM for ambiguous) ────┐
                     │  Hybrid matching (embedding + keyword + participant)│
                     │  LLM judge only for borderline candidates     │
                     │  Merge / Link / Create decision               │
                     └───────────────────────────────────────────────┘
                              │
                              ▼
                        Knowledge Graph Update
```

**Cost allocation per meeting (target: $0.05–0.20):**

| Stage | Method | Estimated cost |
|-------|--------|---------------|
| 1. Segmentation | Heuristic (Python) | $0.00 |
| 2. Entity extraction | spaCy NER (local) | $0.00 |
| 3a. Candidate topics — Tier 1 | KeyBERT + embedding clustering (local) | ~$0.001 (embedding API) |
| 3b. Candidate topics — Tier 2 | Haiku on candidate blocks only | ~$0.02–0.08 |
| 4. Filtering | Rule-based + Haiku classifier | ~$0.01–0.03 |
| 5. Resolution | Sonnet on ambiguous matches only | ~$0.02–0.06 |
| **Total** | | **~$0.05–0.17** |

---

## 2. Definitions

### What is a "topic"

A topic is a work-related subject discussed in a meeting that has organizational consequence — something a reasonable manager or teammate would want tracked. It is NOT just any subject mentioned.

### What is an "entity"

An entity is something **definitive and deterministic** — it cannot be subjective. Entities are facts, not interpretations.

Entities include:
- **People** — "Rahul", "Sarah from engineering", "the CEO"
- **Products / projects** — "Pocket Nori", "the migration project", "PROJ-4521"
- **Companies / organizations** — "Acme Corp", "our Series A investors", "Google"
- **Dates / deadlines** — "March 15", "end of Q3", "next Friday"
- **Artifacts** — "the pricing deck", "Rahul's proposal", "the API spec"
- **Monetary values** — "$50K budget", "15% discount"

Entities do NOT include:
- Concepts ("digital transformation", "agile methodology")
- Themes ("cost reduction", "improving user experience")
- Sentiments ("the team is frustrated")
- Opinions ("I think we should pivot")

These subjective elements belong in the topic's `key_points`, `adjective_signals`, or `decision_made` fields — not as standalone entities.

### What is a "topic arc"

A topic arc is the chronological trail of a single topic across multiple meetings. "Q3 pricing" discussed on March 5, approved on March 10, and assigned on March 12 is one arc with three touchpoints.

### When does a topic fork (not continue)

A topic forks into a **new linked topic** when:
- The **stakeholders change** (strategy team → engineering team)
- The **workstream changes** (strategic decision → tactical execution)
- The **type of work changes** (deciding what to do → doing it)

Example: "Deciding Q3 pricing model" (strategy, CEO + product lead) → fork → "Redesigning pricing page" (execution, design + engineering). These are linked via a `derived_from` relationship, not merged into one arc.

The test: **if you removed the parent topic's decision from history, would the child topic still make sense as-is?** If yes → same arc. If no → fork.

---

## 3. Stage 1: Segmentation (No LLM)

Break the transcript into discussion blocks before any topic extraction. A discussion block is a contiguous segment where the conversation stays on roughly the same subject.

### Why segment first

- Reduces what the LLM needs to process downstream (cost savings)
- Makes topic boundaries explicit
- Each block maps to zero or one candidate topic
- Even 30-second blocks (brief approvals) are properly isolated

### Input

From Recall.ai:
- Transcript text with speaker labels
- Timestamps per utterance
- Speaker diarization (who spoke when)

From Google Calendar (always available):
- Meeting title
- Participant list (names, emails)
- Recurring series info
- Meeting duration

### Segmentation method: Heuristic (no LLM)

Detect subject shifts using deterministic signals:

```python
def segment_transcript(utterances: list[Utterance]) -> list[DiscussionBlock]:
    blocks = []
    current_block_start = 0
    
    for i in range(1, len(utterances)):
        shift_detected = False
        shift_type = None
        
        # Signal 1: Explicit transition phrases (high confidence)
        transition_phrases = [
            "moving on", "next item", "next topic", "let's talk about",
            "switching to", "one more thing", "before we wrap",
            "another thing", "on a different note", "let's shift to",
            "okay so", "alright next", "the other thing I wanted"
        ]
        if any(phrase in utterances[i].text.lower() for phrase in transition_phrases):
            shift_detected = True
            shift_type = "explicit_transition"
        
        # Signal 2: Time gap > 5 seconds between utterances
        if not shift_detected:
            gap = utterances[i].start_time - utterances[i-1].end_time
            if gap > 5.0:  # seconds
                shift_detected = True
                shift_type = "silence_gap"
        
        # Signal 3: Speaker change after extended monologue
        # (same speaker talked for 60+ seconds, new speaker starts new subject)
        # This alone is weak — combine with vocabulary shift
        
        if shift_detected:
            blocks.append(DiscussionBlock(
                block_id=len(blocks),
                start_index=current_block_start,
                end_index=i - 1,
                shift_type=shift_type,
                participants=extract_speakers(utterances[current_block_start:i]),
                duration_seconds=calc_duration(utterances, current_block_start, i-1)
            ))
            current_block_start = i
    
    # Final block
    blocks.append(DiscussionBlock(
        block_id=len(blocks),
        start_index=current_block_start,
        end_index=len(utterances) - 1,
        shift_type="end_of_meeting",
        participants=extract_speakers(utterances[current_block_start:]),
        duration_seconds=calc_duration(utterances, current_block_start, len(utterances)-1)
    ))
    
    return blocks
```

### Segmentation output

```python
class DiscussionBlock(BaseModel):
    block_id: int
    start_index: int               # First utterance index
    end_index: int                  # Last utterance index
    start_timestamp: float | None   # Seconds from meeting start
    end_timestamp: float | None
    shift_type: str                 # "explicit_transition" | "silence_gap" | "speaker_shift" | "end_of_meeting"
    participants: list[str]         # Speakers in this block
    duration_seconds: float
    utterance_count: int
    text: str                       # Concatenated text of all utterances in block
```

### Known limitations of heuristic segmentation

- **Misses semantic shifts without pauses or transition phrases.** If someone smoothly pivots from pricing to hiring without saying "moving on," heuristic segmentation won't catch it. This is acceptable for v1 — the topic extraction LLM in Stage 3 can still identify multiple topics within a single block.
- **Over-segments on natural pauses.** A 6-second pause might just be someone thinking, not a topic shift. Mitigation: merge adjacent blocks if they're under 3 utterances and the same speakers are involved.
- **Target accuracy: >70% of real subject shifts captured.** This is lower than the previous doc's 85% target because we're removing the LLM from segmentation. The tradeoff is worth it — segmentation is a preprocessing step, not the final answer. Imperfect blocks still reduce LLM cost downstream.

---

## 4. Stage 2: Entity Extraction (No LLM)

Extract deterministic entities from each discussion block using NER and pattern matching. No LLM needed — entities are facts, not judgments.

### Method: spaCy + custom patterns

```python
import spacy

nlp = spacy.load("en_core_web_lg")

def extract_entities(block: DiscussionBlock, known_participants: list[str]) -> list[Entity]:
    doc = nlp(block.text)
    entities = []
    
    for ent in doc.ents:
        if ent.label_ == "PERSON":
            # Match against known participant list for normalization
            normalized = match_to_participant(ent.text, known_participants)
            entities.append(Entity(type="person", value=normalized or ent.text, raw=ent.text))
        
        elif ent.label_ == "ORG":
            entities.append(Entity(type="company", value=ent.text, raw=ent.text))
        
        elif ent.label_ == "DATE":
            entities.append(Entity(type="date", value=ent.text, raw=ent.text))
        
        elif ent.label_ == "MONEY":
            entities.append(Entity(type="monetary_value", value=ent.text, raw=ent.text))
        
        elif ent.label_ == "PRODUCT":
            entities.append(Entity(type="product", value=ent.text, raw=ent.text))
    
    # Custom pattern matching for things spaCy misses
    # Deadlines: "by Friday", "due March 15", "end of Q3"
    deadline_patterns = extract_deadline_patterns(block.text)
    entities.extend(deadline_patterns)
    
    # Project codes: "PROJ-4521", "JIRA-123", ticket references
    project_codes = extract_project_codes(block.text)
    entities.extend(project_codes)
    
    # Artifact references: "the pricing deck", "Sarah's proposal"
    # These are harder — use possessive + noun patterns
    artifacts = extract_artifact_references(block.text)
    entities.extend(artifacts)
    
    return deduplicate_entities(entities)
```

### Entity output

```python
class Entity(BaseModel):
    type: str          # "person" | "company" | "product" | "date" | "deadline" | "monetary_value" | "artifact" | "project_code"
    value: str         # Normalized value
    raw: str           # Original text as spoken
    confidence: float  # spaCy confidence score
```

### Why entity extraction happens before topic identification

- Entities are deterministic — same input always produces same output (at temperature=0 with spaCy)
- Entity density is a signal for topic identification in Stage 3 (blocks with more entities are more likely to contain real topics)
- Entity overlap across blocks/meetings is a signal for resolution in Stage 5
- Entities extracted here get attached to candidate topics in Stage 3 — the LLM doesn't need to re-extract them

### spaCy accuracy on conversational text

spaCy's NER is trained primarily on formal text (news, web). Conversational transcripts have messier language ("so Rahul was like, we should just go with tiered"). Expect:
- Person names: ~90% recall (misses informal references like "the new guy")
- Companies: ~80% recall (misses abbreviations and informal names)
- Dates: ~85% recall (catches "March 15" but may miss "end of next week")
- Products: ~60% recall (this is spaCy's weakest category for informal text)

Mitigation: the LLM in Stage 3 can catch entities that spaCy missed, but spaCy handles the bulk for free.

---

## 5. Stage 3: Candidate Topic Identification (Two-Tier)

This is the core cost optimization. Split topic identification into a cheap deterministic pass and a targeted LLM pass.

### Tier 1: Non-LLM signals (runs on every block, cost ≈ $0)

For each discussion block, compute a **topic candidacy score** from deterministic signals:

```python
def compute_candidacy_score(block: DiscussionBlock, entities: list[Entity]) -> float:
    score = 0.0
    
    # Signal 1: Entity density
    # Blocks with more entities are more likely to contain real topics
    entity_count = len(entities)
    if entity_count >= 3:
        score += 0.3
    elif entity_count >= 1:
        score += 0.15
    
    # Signal 2: Multi-speaker engagement
    # More than one person spoke substantively (not just "yeah" or "okay")
    substantive_speakers = count_substantive_speakers(block)
    if substantive_speakers >= 2:
        score += 0.25
    
    # Signal 3: Adjective/qualifier signals (keyword detection, no LLM)
    adjective_keywords = {
        "critical": ["urgent", "asap", "blocking", "critical", "blocker", 
                     "high priority", "escalat"],
        "high": ["important", "deadline", "management", "leadership",
                 "client", "customer", "partner", "compliance", "regulatory",
                 "must", "need to", "required"],
        "low": ["nice to have", "eventually", "low priority", "backlog",
                "parking lot", "someday", "brainstorm", "just an idea"]
    }
    block_lower = block.text.lower()
    for level, keywords in adjective_keywords.items():
        if any(kw in block_lower for kw in keywords):
            score += 0.2 if level in ("critical", "high") else 0.05
            break
    
    # Signal 4: Decision/commitment language
    decision_phrases = ["decided", "approved", "let's go with", "agreed",
                       "we'll do", "action item", "i'll", "you'll", 
                       "by friday", "by end of", "due date", "follow up"]
    if any(phrase in block_lower for phrase in decision_phrases):
        score += 0.2
    
    # Signal 5: Block duration / utterance count
    # Very short blocks (< 3 utterances) are less likely topics UNLESS
    # they contain decision language (handled above)
    if block.utterance_count >= 5:
        score += 0.1
    
    # Signal 6: Keyphrase extraction (KeyBERT — local, fast)
    keyphrases = keybert_extract(block.text, top_n=5)
    if len(keyphrases) >= 2 and keyphrases[0].score > 0.4:
        score += 0.15
    
    # Signal 7: Speaker seniority (if role mapping available)
    if has_executive_speaker(block.participants):
        score += 0.25  # Executive spoke in this block → auto-boost
    
    return min(score, 1.0)
```

**Tier 1 threshold:** Blocks scoring **≥ 0.3** are candidate topics and proceed to Tier 2.

**What this catches without any LLM:**
- Blocks with entities + multiple speakers + decision language → score ~0.7+ → obvious topic
- Blocks where a CEO asks a question about something with a deadline → score ~0.6+ → obvious topic
- Blocks with only social chat, no entities, single speaker → score ~0.05 → filtered out

**What this misses (and that's okay for Tier 1):**
- The "brief approval" — 2 utterances, 1 entity, maybe no adjective keywords. Might score ~0.15 and get filtered. BUT: if it contains decision language ("approved", "let's go with"), Signal 4 catches it (+0.2) and it passes.
- Nuanced discussions without explicit markers. These are the long-tail cases where Tier 2's LLM earns its cost.

**Estimated Tier 1 pass-through rate:** ~40-60% of blocks proceed to Tier 2. For a typical 45-minute meeting with ~12-18 blocks, that's 5-10 blocks going to the LLM instead of all 12-18. Cost savings: 40-60% reduction in LLM tokens.

### Tier 2: LLM validation and enrichment (Haiku, only on candidates)

For each block that passes Tier 1, send to Haiku (cheapest, fastest) with a focused prompt. The LLM's job is NOT to find topics from scratch — it's to validate and enrich what Tier 1 already flagged.

**Input to Haiku:** Only the candidate block's text + its pre-extracted entities + meeting metadata.

```
MEETING CONTEXT:
- Title: "{meeting_title}"
- Category: {category_from_title_keywords}
- Participants: {participant_names_and_roles}
- Recurring: {series_name or "ad-hoc"}

DISCUSSION BLOCK (Block {block_id} of {total_blocks}):
"""
{block.text}
"""

PRE-EXTRACTED ENTITIES:
{entities from Stage 2, formatted as list}

TIER 1 SIGNALS:
- Candidacy score: {score}
- Adjective signals detected: {list}
- Decision language detected: {yes/no}
- Keyphrases: {list}

TASK:
1. Is this block a substantive work topic? Answer yes or no.
   - If NO, provide skip_reason and stop.
   - If YES, continue.

2. Extract the topic:
   - name: Use verb+noun format ("Finalizing Q3 pricing", not "pricing")
   - type: "discussion" | "decision" | "status_update" | "brainstorm" | "action_planning"
   - key_points: Max 3 substantive points
   - decision_made: If a decision was reached, what was it? null if none.
   - commitments: [{owner, action, deadline}] — who committed to doing what by when?
   - open_questions: Unresolved items
   - related_keywords: Alternate phrasings, abbreviations, codenames — 
     CRITICAL for downstream matching
   - source_context: "client_request" | "leadership_directive" | "internal" | 
     "compliance" | null

3. Validate pre-extracted entities:
   - Confirm or correct the entities from Stage 2
   - Add any entities spaCy missed (especially informal references)

DO NOT extract:
- Personal topics (vet appointments, weekend plans, family logistics)
- Social check-ins ("how was your weekend")  
- Logistics ("here's the zoom link", "can you hear me")
- Announcements nobody engaged with

BRIEF APPROVAL RULE:
If this block is short (< 5 utterances) but contains an approval, 
rejection, or decision about a previously discussed subject, this is 
HIGH PRIORITY. Extract it with type="decision" and fill in decision_made.
```

### Tier 2 output schema

```python
class CandidateTopic(BaseModel):
    is_valid_topic: bool
    skip_reason: str | None          # If not valid: "personal", "check_in", "logistics", "no_substance"
    
    # Only populated if is_valid_topic = True
    name: str | None                 # Verb+noun format
    type: str | None                 # "discussion" | "decision" | "status_update" | "brainstorm" | "action_planning"
    key_points: list[str]
    decision_made: str | None
    commitments: list[dict] | None   # [{owner, action, deadline}]
    open_questions: list[str]
    related_keywords: list[str]      # Critical for resolution
    adjective_signals: list[str]     # Extracted from speech: "urgent", "blocking", "client ask"
    priority_level: str              # "critical" | "high" | "normal" | "low"
    source_context: str | None       # "client_request" | "leadership_directive" | "internal" | "compliance"
    
    # From Stage 2 (confirmed/corrected)
    entities: list[Entity]
    
    # Metadata
    discussion_block_id: int
    meeting_title_mapping: str | None  # "primary" | "tangential" | null
    confidence_score: float
```

### Cost estimate for Tier 2

A typical candidate block is ~200-500 words. Haiku processes this at:
- Input: ~400-700 tokens per block
- Output: ~200-400 tokens
- At Haiku pricing (~$0.25/M input, $1.25/M output): **~$0.001 per block**
- 5-10 candidate blocks per meeting: **~$0.005–0.01 per meeting**

This is well within the $0.05–0.20 budget, leaving room for Stage 5 resolution.

---

## 6. Stage 4: Filtering

Rule-based filtering on Tier 2 output. No LLM needed — these are deterministic rules.

### 6.1 Work vs. personal classification

Already handled by Haiku in Tier 2 (`is_valid_topic` + `skip_reason`). But add a safety net:

```python
PERSONAL_KEYWORDS = ["vet", "doctor", "dentist", "kids", "school pickup",
                     "grocery", "gym", "personal", "apartment", "landlord",
                     "birthday party", "vacation booking"]

def is_personal_override(topic: CandidateTopic) -> bool:
    """Catch personal topics that Haiku missed."""
    text = f"{topic.name} {' '.join(topic.key_points)}".lower()
    if any(kw in text for kw in PERSONAL_KEYWORDS):
        # Exception: topics that affect work
        work_override = ["parental leave", "working from home", "sick leave",
                        "availability", "out of office"]
        if any(wo in text for wo in work_override):
            return False
        return True
    return False
```

### 6.2 Seniority-based promotion

```python
SENIORITY_TIERS = {
    "executive": ["ceo", "cto", "cfo", "coo", "vp", "svp", "evp", 
                  "partner", "board", "founder", "president"],
    "manager": ["director", "senior manager", "manager", "team lead", "head of"],
    "ic": None  # Default
}

def apply_seniority_promotion(topic: CandidateTopic, 
                               block: DiscussionBlock,
                               participant_roles: dict) -> CandidateTopic:
    """If an executive spoke in this block, promote the topic."""
    for speaker in block.participants:
        role = participant_roles.get(speaker, "ic")
        if role == "executive":
            topic.speaker_seniority = "executive"
            if topic.priority_level in ("normal", "low"):
                topic.priority_level = "high"
            return topic
        elif role == "manager":
            topic.speaker_seniority = topic.speaker_seniority or "manager"
    
    return topic
```

### 6.3 Qualification gate

After all filters, a topic must meet AT LEAST TWO of:

1. **Actionability** — commitments or open_questions exist
2. **Multiple participants** — more than one person spoke substantively
3. **Temporal relevance** — references past discussion or has future deadline
4. **Position/decision** — decision_made is not null, or key_points contain opinions

**Auto-qualify (skip the 2-of-4 test):**
- speaker_seniority = "executive"
- type = "decision"
- priority_level = "critical"

**When in doubt, keep it.** Users can dismiss noise; they can't recover missed topics.

---

## 7. Stage 5: Resolution (Merge, Link, or Create)

Validated topics are resolved against the existing knowledge graph.

### 7.1 Hybrid matching for merge candidates

Three signals combined:

```python
def find_merge_candidates(new_topic: CandidateTopic, user_id: str) -> list[MergeCandidate]:
    # Signal 1: Semantic similarity (pgvector)
    embedding_text = f"{new_topic.name} {' '.join(new_topic.related_keywords)}"
    semantic_candidates = pgvector_search(embed(embedding_text), user_id, top_k=10)
    
    # Signal 2: Keyword overlap (tsvector BM25)
    keyword_candidates = tsvector_search(
        new_topic.related_keywords + new_topic.name.split(), user_id, top_k=10
    )
    
    # Signal 3: Entity overlap
    # Shared people + shared projects = strong merge signal
    entity_candidates = entity_overlap_search(new_topic.entities, user_id, top_k=10)
    
    # Signal 4: Participant overlap
    participant_boost = get_participant_overlap_scores(
        new_topic.participants_involved, user_id
    )
    
    # Combine with weights
    combined = merge_and_rank(
        semantic=semantic_candidates,     # weight: 0.35
        keyword=keyword_candidates,       # weight: 0.25
        entity=entity_candidates,         # weight: 0.25
        participant=participant_boost,     # weight: 0.15
    )
    
    return [c for c in combined if c.score > CANDIDATE_THRESHOLD]
```

**Note:** Entity overlap is now a first-class signal (it wasn't in the previous doc). If two topics mention the same person + same project + same deadline, they're almost certainly the same topic regardless of how differently they're named.

### 7.2 Resolution decision

Three tiers of resolution, each with different cost profiles:

```
High confidence (combined score > 0.85):
  → Auto-merge. No LLM needed. Log for review.
  
Medium confidence (0.55 < score ≤ 0.85):
  → LLM resolution (Sonnet). Ask: same, related, or unrelated?
  
Low confidence (score ≤ 0.55):
  → Create new topic. No LLM needed.
```

**Only the medium-confidence band requires Sonnet.** Based on observed distributions, this is typically 20-30% of candidates. For a meeting with 4-6 validated topics and 3-5 merge candidates each, that's ~3-8 Sonnet calls per meeting.

### 7.3 Sonnet resolution prompt (only for medium-confidence candidates)

```
You are determining whether a newly extracted meeting topic matches 
existing topics in a personal knowledge graph.

NEW TOPIC:
- Name: "{new_topic.name}"
- Keywords: {new_topic.related_keywords}
- Entities: {new_topic.entities}
- Type: {new_topic.type}
- Key points: {new_topic.key_points}
- Meeting: {meeting_title}, {date}
- Participants: {participants}

CANDIDATE MATCHES:
{for each candidate}
- [{id}] "{label}"
  Aliases: {aliases}
  Last discussed: {last_mentioned_at}
  Participants: {participant_names}
  Entities: {entities}
  Status: {status}
{end for}

For each candidate:
{
  "candidate_id": "...",
  "relationship": "same | related | derived_from | unrelated",
  "confidence": 0.0-1.0,
  "reasoning": "one sentence"
}

RULES:
1. "same" = same ongoing topic. Add to its arc.
2. "related" = share context but are distinct topics. Create a link.
3. "derived_from" = new topic was spawned by a decision in the old topic. 
   Create a directional link. Example: "Deciding Q3 pricing" → 
   derived_from → "Redesigning pricing page."
4. "unrelated" = similarity was misleading. Do not link.

FORK TEST for "same" vs "derived_from":
- Did the stakeholders change?
- Did the workstream change (strategy → execution)?
- Would the new topic exist independently of the old topic's decision?
If YES to any → "derived_from", not "same".

5. When in doubt between "same" and "related", choose "related".
   False merges corrupt the graph.
6. Entity overlap (same people + same project) is the strongest signal.
```

### 7.4 Merge mechanics: alias accumulation

On merge, don't replace — accumulate:

```python
def merge_topics(existing_topic_id: str, new_topic: CandidateTopic):
    existing = get_topic(existing_topic_id)
    
    # Accumulate aliases
    if new_topic.name != existing.label:
        existing.aliases.append(new_topic.name)
    existing.aliases.extend(new_topic.related_keywords)
    existing.aliases = list(set(existing.aliases))
    
    # Accumulate entities
    existing.entities = deduplicate_entities(existing.entities + new_topic.entities)
    
    # Escalate priority if warranted
    if PRIORITY_RANK[new_topic.priority_level] > PRIORITY_RANK[existing.priority_level]:
        existing.priority_level = new_topic.priority_level
    
    # Escalate seniority if warranted
    if SENIORITY_RANK.get(new_topic.speaker_seniority, 0) > SENIORITY_RANK.get(existing.speaker_seniority, 0):
        existing.speaker_seniority = new_topic.speaker_seniority
    
    # Update temporal markers
    existing.last_mentioned_at = now()
    
    # Link conversation
    link_topic_to_conversation(existing.id, new_topic.conversation_id)
    
    # Re-embed with accumulated context
    new_embedding = embed(f"{existing.label} {' '.join(existing.aliases)}")
    update_topic_embedding(existing.id, new_embedding)
```

**Flywheel effect:** Frequently discussed topics accumulate aliases and entities, making future matching easier. The graph improves with use.

---

## 8. Meeting Metadata Injection

Calendar metadata is always available. Use it as a pre-processing signal before any extraction.

### Title keyword classification (Python dictionary, no LLM)

```python
MEETING_CATEGORY_SIGNALS = {
    "strategy": {
        "keywords": ["strategy", "planning", "roadmap", "vision", "quarterly review", "okr"],
        "extraction_hint": "Extract decisions and directional choices. Everything discussed carries strategic weight."
    },
    "review": {
        "keywords": ["review", "retro", "retrospective", "postmortem", "debrief"],
        "extraction_hint": "Extract what worked, what didn't, and action items."
    },
    "standup": {
        "keywords": ["standup", "sync", "check-in", "daily", "weekly sync"],
        "extraction_hint": "Extract blockers, progress updates, and commitments."
    },
    "one_on_one": {
        "keywords": ["1:1", "one-on-one", "1-on-1", "one on one"],
        "extraction_hint": "Extract career topics, feedback, and private commitments. May contain personal topics — filter carefully."
    },
    "crisis": {
        "keywords": ["urgent", "escalation", "incident", "war room", "outage", "p0", "sev1"],
        "extraction_hint": "Everything discussed is high priority. Extract all decisions."
    },
    "external": {
        "keywords": ["sales", "customer", "demo", "pitch", "client", "partner"],
        "extraction_hint": "Extract client requests, objections, commitments, and follow-ups."
    },
    "hiring": {
        "keywords": ["interview", "candidate", "hiring", "recruitment"],
        "extraction_hint": "Extract evaluation criteria and hiring decisions."
    },
    "governance": {
        "keywords": ["board", "investor", "fundraise", "board meeting"],
        "extraction_hint": "Extract commitments, questions raised, and strategic signals."
    }
}

def classify_meeting(title: str, participants: list[str], 
                      participant_roles: dict) -> MeetingContext:
    title_lower = title.lower()
    categories = []
    for category, config in MEETING_CATEGORY_SIGNALS.items():
        if any(kw in title_lower for kw in config["keywords"]):
            categories.append(category)
    
    has_executive = any(
        participant_roles.get(p) == "executive" for p in participants
    )
    
    return MeetingContext(
        title=title,
        categories=categories or ["general"],
        extraction_hints=[MEETING_CATEGORY_SIGNALS[c]["extraction_hint"] for c in categories],
        has_executive=has_executive,
        participant_count=len(participants)
    )
```

---

## 9. Non-Determinism Mitigation

### The problem

Different runs on the same transcript can produce different topic names, different numbers of topics, and different key_points. This is inherent to LLMs.

### Mitigation strategy (layered)

1. **Minimize LLM surface area.** Stages 1, 2, and most of 4 are deterministic. The LLM only touches Stage 3 Tier 2 (validation/enrichment) and Stage 5 (ambiguous resolution). Less LLM = less variance.

2. **Temperature = 0** for all LLM calls.

3. **Structured output via Pydantic.** The `instructor` library enforces schema compliance. The LLM can't return freeform text — only valid `CandidateTopic` objects.

4. **Verb+noun naming constraint.** Fewer valid phrasings → more consistency. "Finalizing Q3 pricing" has less naming variance than an unconstrained label.

5. **Related keywords absorb naming variance.** Even if the LLM names a topic "Deciding Q3 pricing" vs. "Finalizing pricing model," the keywords ["pricing", "tiered", "Q3", "monetization"] will likely overlap. The resolution layer (Stage 5) catches this via keyword matching.

6. **Canonical naming on merge.** Once a topic merges into an existing node, the canonical label stays stable. Future extractions resolve against this stable label.

7. **Entities are deterministic anchors.** spaCy NER extracts the same entities every time. Even if topic names vary, entity overlap provides a stable matching signal.

8. **Idempotency test (part of annotation plan).** Run the same 5 transcripts through the pipeline 3 times each. Measure variance in: number of topics extracted, topic names, entity lists, merge decisions. Acceptable variance: topic names may differ in wording but the resolution layer should produce identical graph states >90% of the time.

---

## 10. Adjective Signal Reference

People signal importance through qualifying language. Detect these via keyword matching (Stage 3 Tier 1) and confirm via LLM (Stage 3 Tier 2).

| What someone says | adjective_signal | priority_level | source_context |
|---|---|---|---|
| "urgent / ASAP / blocking us" | "urgent" | critical | — |
| "management ask / leadership priority" | "leadership_priority" | high | leadership_directive |
| "client feedback / customer escalation" | "client_escalation" | high | client_request |
| "partner recommendation" | "partner_input" | high | client_request |
| "blocker / dependency / bottleneck" | "blocker" | critical | — |
| "deadline is Friday / due next week" | "deadline" | high | — |
| "compliance / regulatory / legal" | "compliance" | high | compliance |
| "nice-to-have / low priority" | "deprioritized" | low | — |
| "just an idea / brainstorming" | "ideation" | low | internal |
| CEO/VP states opinion or asks question | (seniority promotion) | auto-promote to high | leadership_directive |

---

## 11. Topic Arc Rules

### Continuation (same arc)
The same topic discussed across multiple meetings with the same workstream and stakeholders. The graph adds a new touchpoint to the existing topic node.

**Examples:**
- Meeting 1: "Discussing Q3 pricing options" → Meeting 3: "Approving tiered pricing" → same arc
- Meeting 2: "Reviewing API performance" → Meeting 5: "API latency still above target" → same arc

### Fork (new linked topic)
A new topic spawned by a decision or outcome of the parent topic. Different workstream, different stakeholders, different type of work.

**Examples:**
- "Deciding Q3 pricing model" (strategy) → fork → "Redesigning pricing page" (design/eng)
- "Approving new hire for backend" (hiring) → fork → "Onboarding new backend engineer" (team ops)

**Graph representation:**
```
[Deciding Q3 pricing model] ──derived_from──→ [Redesigning pricing page]
```
The `derived_from` link preserves lineage. The topic dashboard can show: "This topic originated from a decision made in [parent topic] on [date]."

### Related (distinct but contextually linked)
Two topics that share context but neither spawned the other. They exist independently but benefit from being linked.

**Examples:**
- "Q3 pricing model" and "Competitor pricing analysis" — related but independent
- "API performance review" and "Infrastructure cost optimization" — related but distinct workstreams

**Graph representation:**
```
[Q3 pricing model] ──related──→ [Competitor pricing analysis]
```

---

## 12. Implementation Sequence

| Step | Stage | Method | Depends on | Effort |
|------|-------|--------|-----------|--------|
| 1 | Annotation | Manually annotate 20-30 transcripts | Nothing | 2-3 days |
| 2 | Stage 1 | Heuristic segmentation | Step 1 for validation | 2-3 days |
| 3 | Stage 2 | spaCy NER + custom patterns | Step 2 | 2-3 days |
| 4 | Stage 3 Tier 1 | Candidacy scoring (KeyBERT + signals) | Steps 2, 3 | 3-4 days |
| 5 | Stage 3 Tier 2 | Haiku validation prompt | Step 4 | 2-3 days |
| 6 | Stage 4 | Filtering rules | Step 5 | 1-2 days |
| 7 | Stage 5 | Hybrid matching + Sonnet resolution | Steps 5, 6 | 3-5 days |
| 8 | Evaluation | Run pipeline on annotated transcripts, measure metrics | All | 2-3 days |

**Total estimated effort: ~3-4 weeks**

### Annotation plan (Step 1)

Before building anything, annotate 20-30 of your own real meeting transcripts:

For each transcript:
1. Manually segment into discussion blocks (mark where subjects shift)
2. For each block, note:
   - Is this a topic? (yes/no)
   - If yes: what's the topic name?
   - Is it work-related or personal?
   - What entities are present?
   - What's the priority? Why?
3. Across transcripts, note which topics are the same (should merge)
4. Note which topics are related but distinct
5. Note any forks (topic B derived from topic A)

This annotation set becomes:
- Ground truth for tuning Tier 1 candidacy thresholds
- Ground truth for measuring extraction precision/recall
- Ground truth for evaluating merge accuracy
- Training data if you later want to fine-tune a classifier
- Evaluation dataset for the research paper

**Store annotations in a structured format (JSON or CSV) alongside transcript files.**

---

## 13. Success Metrics

| Metric | Target | How to measure |
|--------|--------|---------------|
| Segmentation: real shifts captured | >70% | Compare against annotated block boundaries |
| Entity extraction recall (spaCy) | >80% | Compare against annotated entities |
| Tier 1 candidate precision | >60% | % of Tier 1 candidates that are real topics |
| Tier 1 candidate recall | >90% | % of real topics that Tier 1 flags as candidates |
| Topic extraction precision (after Tier 2) | >90% | % of final topics that are real |
| Topic extraction recall (after Tier 2) | >80% | % of real topics that are extracted |
| Work/personal classification accuracy | >95% | Compare against annotations |
| Merge precision | >85% | % of merges that are correct |
| Merge recall | >65% | % of real cross-meeting connections found |
| False merge rate | <10% | % of merges that are incorrect |
| Pipeline cost per meeting | $0.05–0.20 | Track API costs |
| Idempotency (same graph state on re-run) | >90% | Run same transcript 3x, compare graph output |

**Tier 1 recall target is deliberately high (>90%).** It's okay for Tier 1 to have false positives (low precision) because Tier 2 filters them. It's NOT okay for Tier 1 to miss real topics (low recall) because they never reach the LLM. Tune the candidacy threshold conservatively — bias toward including more candidates, not fewer.

---

## 14. What This Enables Downstream

With this pipeline:
- **Topic arcs with lineage:** "Q3 pricing was raised by Client X on March 5, discussed March 8, approved by CEO March 10, forked into 'Pricing page redesign' on March 12."
- **Priority dashboard:** Filter by critical/high/normal/low.
- **Seniority-aware briefs:** Before a CEO meeting, surface all topics the CEO previously engaged with.
- **Source tracking:** "Show me everything from client conversations" vs. "internal initiatives."
- **Entity-anchored search:** "What has Rahul committed to?" pulls all topics where Rahul is an entity with a commitment.
- **Off-agenda detection:** Meetings producing topics unrelated to their title.
- **Cost transparency:** Know exactly what each meeting costs to process.

All running on: Recall.ai (transcription) → spaCy (entities) → KeyBERT (keyphrases) → Haiku (validation) → Sonnet (resolution) → PostgreSQL + pgvector (storage).
