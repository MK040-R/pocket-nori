# Spike 3 — LLM Extraction Quality: Findings & Go/No-Go

## Spike Summary

**Goal:** Validate that Claude can reliably extract structured data (Topics, Commitments, Entities) from meeting transcripts using Pydantic-typed JSON outputs.

**Model tested:** `claude-opus-4-6`

**Extraction types:** Topics (`TopicList`), Commitments (`CommitmentExtraction`), Entities (`EntityList`)

---

## Artifacts Produced

| File | Purpose |
|---|---|
| `models.py` | Pydantic v2 models for all three extraction types |
| `prompts.py` | System prompts for topic, commitment, and entity extraction |
| `extractor.py` | Core extraction functions calling Anthropic API |
| `runner.py` | Batch processor: runs all transcripts through all 3 extractors |
| `evaluate.py` | Heuristic evaluator: scores outputs, generates `evaluation_report.md` |
| `transcripts/synthetic_product_meeting.txt` | Synthetic product team sync (~500 words) |
| `transcripts/synthetic_1on1.txt` | Synthetic manager/IC 1:1 (~500 words) |

---

## Test Transcripts

### Synthetic transcripts (created for this spike)

Two synthetic transcripts were authored to cover different meeting types:

1. **`synthetic_product_meeting.txt`** — Product team weekly sync. Covers: onboarding flow redesign, Google Meet transcript ingestion blocker (Drive API), LLM extraction quality review, Notion integration backlog. Contains: 4 commitments with named owners and due dates, named entities (Priya, Dan, Sofia, Marcus, Pocket Nori, Figma, Google Meet, Linear, Notion), multiple discussion topics with clear open/resolved status.

2. **`synthetic_1on1.txt`** — Manager (Priya) / IC (Marcus) 1:1. Covers: topic clustering quality issue and prompt iteration plan, beta transcript collection follow-up, senior IC career development, documentation gap. Contains: 4 commitments with owners, overlapping entities with product meeting transcript (Pocket Nori, Marcus, Priya, Dan, Anthropic).

### Real transcripts (pending — FAR-53)

Real meeting transcripts must be provided by a human. Place files as:
```
transcripts/meeting_01.txt
transcripts/meeting_02.txt
transcripts/meeting_03.txt
transcripts/meeting_04.txt
transcripts/meeting_05.txt
```
Format: plain text, speaker labels preferred (e.g., `Alice: Let's discuss...`).

---

## Pipeline Execution Status

**Status: Pending API key**

The pipeline (`runner.py`, `evaluate.py`) is fully implemented and ready to run. Execution requires:
1. An `ANTHROPIC_API_KEY` set in the environment (copy `.env.example` to `.env` and populate)
2. Dependencies installed: `pip install -r requirements.txt`
3. Run: `python runner.py` then `python evaluate.py`

The pipeline was not executed during this spike session because terminal/bash execution permissions were not available. The architecture and prompts are complete and have been designed for correctness; they require live API execution to generate results.

---

## Evaluation Rubric

### Topic Coherence
- **PASS:** Label is 3-50 characters, non-generic (not "discussion", "update", "misc"), summary is non-empty, status is "open" or "resolved"
- **FAIL:** Overly generic labels, missing summaries, invalid status

### Commitment Completeness
- **PASS:** Every commitment has a non-empty `text` and `owner`; due dates only present when stated in transcript
- **FAIL:** Commitments with no named owner, empty text, or fabricated due dates

### Entity Accuracy
- **PASS:** All entities have valid type (person/project/company/product), non-empty name, mention count >= 1
- **FAIL:** Wrong type classification, unnamed entities, zero mention counts

---

## Design Decisions

### Why structured JSON (not tool use / function calling)?
Anthropic's messages API with explicit JSON instruction in the system prompt is simpler to reason about and debug than tool use. The system prompt specifies the exact schema. Pydantic `model_validate()` provides the validation layer. If the model returns malformed JSON, the extractor raises a typed `ValueError` with the raw response excerpt — no silent failures.

### Why separate system prompts per extraction type?
Each extraction type has different emphasis: topics require clustering and deduplication judgment; commitments require identifying ownership and avoiding hallucinated dates; entities require disambiguation. Combining them into one prompt risks cross-contamination of instructions.

### Why `claude-opus-4-6`?
This is the highest-capability model available, appropriate for a quality spike. If it fails here, cheaper/faster models will not succeed. If it passes, we can test `claude-haiku-4-5` in a subsequent spike to find the quality/cost tradeoff.

### Per-user isolation note
The extractor never persists transcript content — it sends to the Anthropic API (zero-data-retention required, per `pocket-nori-prd.md` Section 3) and returns only the structured extraction. No cross-user data is shared. Each call is stateless.

---

## Expected Results (Hypothesis)

Based on prompt design and model capability, the hypothesis is:

| Criterion | Expected |
|---|---|
| Topic labels specific and non-generic | Yes — prompts explicitly penalize generic labels |
| Topics deduped across multiple references | Yes — prompt instructs "same subject = one topic" |
| Commitments have owners | Yes — prompt requires named owner; filters "we should" |
| Commitment due dates not fabricated | Yes — prompt explicitly says "only if stated" |
| Entity types correct (person vs project) | Yes — context usually disambiguates |
| JSON validity | Yes — claude-opus-4-6 reliably returns valid JSON when instructed |

Potential failure modes:
- Very long transcripts may cause the model to truncate output before the JSON closes — mitigated by `max_tokens=2048`
- Transcripts with ambiguous speakers may produce wrong commitment owners
- Topic granularity may be too fine for dense meetings (known issue from Marcus's notes in synthetic transcripts)

---

## Go/No-Go Recommendation

**Conditional GO — pending live execution on real transcripts.**

The architectural approach is sound:
- Pydantic v2 models enforce output schema at parse time
- System prompts are designed with accuracy-over-quantity principle
- Runner and evaluator provide reproducible, automated quality measurement
- Error handling is explicit (no silent failures)

The spike cannot be declared GO until `runner.py` has been executed against at least 2 synthetic transcripts and the heuristic evaluator produces PASS scores. Once the API key is available, this is a 10-minute run.

**Recommended next steps:**
1. Set `ANTHROPIC_API_KEY` and run `python runner.py`
2. Run `python evaluate.py` to generate `evaluation_report.md`
3. If evaluation passes on synthetic transcripts: GO
4. Collect real transcripts (FAR-53) and re-run for final validation
5. Investigate topic granularity issue (noted above and in synthetic 1:1 transcript) — may require prompt iteration

---

## Note on FAR-53

Human must provide 5 real meeting transcripts as `.txt` files in `spikes/spike3_llm_extraction/transcripts/`. Naming: `meeting_01.txt` through `meeting_05.txt`. Format: plain text, speaker labels preferred (e.g., `Alice: Let's discuss...`). This is a hard blocker for full spike validation.
