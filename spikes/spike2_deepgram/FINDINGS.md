# Spike 2: Deepgram Accuracy Validation — Findings

**Status:** Pending human-provided recordings — automated code scaffolding complete.

**Spike goal:** Determine whether Deepgram Nova-3 meets Farz's accuracy and diarization requirements for real meeting audio, and produce a go/no-go recommendation.

---

## 1. Deepgram Nova-3 Overview

| Property | Value |
|---|---|
| Model | Nova-3 (released 2024) |
| Claimed WER (English) | ~5–8% on general speech; lower for clear audio |
| Diarization | Built-in (`diarize=True`), no extra charge |
| Smart formatting | Punctuation, numbers, dates auto-formatted |
| Latency (pre-recorded) | ~0.5–3s per minute of audio (varies by file size) |
| Pricing (as of early 2025) | ~$0.0043/min (pay-as-you-go); volume discounts available |
| Data retention | Deepgram claims zero data retention for API customers — **verify this in their DPA before production use** |
| Languages | 30+ languages; English has best accuracy |

**Source:** https://developers.deepgram.com/docs/nova-3

---

## 2. Test Methodology

- **Script:** `test_deepgram.py`
- **Model:** `nova-3`
- **Options:** `diarize=True`, `punctuate=True`, `smart_format=True`, `language="en"`
- **Input:** 3 real multi-speaker meeting recordings (≥5 min each)
- **Output:** JSON transcript files in `transcripts_output/`
- **Accuracy evaluation:** `evaluate_accuracy.py` — WER against manually verified reference
- **Diarization evaluation:** `evaluate_diarization.py` — speaker count accuracy, turn quality

---

## 3. Results

> Fill this table after running `test_deepgram.py` and the evaluation scripts with real recordings.

| File | Duration | Words | Speakers (detected / actual) | Confidence | WER | Time |
|---|---|---|---|---|---|---|
| recording_1 | — | — | — / — | — | — | — |
| recording_2 | — | — | — / — | — | — | — |
| recording_3 | — | — | — / — | — | — | — |
| **Avg** | — | — | — | — | — | — |

---

## 4. Evaluation Rubric

### 4.1 Transcription Accuracy (WER)

| WER | Rating | Decision |
|---|---|---|
| < 5% | Excellent | Go |
| 5–10% | Acceptable | Go (with monitoring) |
| 10–20% | Marginal | Conditional — investigate audio quality |
| > 20% | Failing | No-Go |

**Farz target:** WER < 10% on typical meeting audio.

### 4.2 Speaker Diarization

| Metric | Excellent | Acceptable | Failing |
|---|---|---|---|
| Speaker count accuracy | Exact match | Off by 1 | Off by 2+ |
| Consistency score | > 0.90 | 0.75–0.90 | < 0.75 |
| Avg words per turn | > 20 | 10–20 | < 10 (over-segmented) |

**Farz target:** Speaker count exact or off by 1; consistency ≥ 0.80.

### 4.3 Latency

| Real-time factor | Rating |
|---|---|
| < 0.2x | Excellent (5-min file done in < 1 min) |
| 0.2–0.5x | Acceptable |
| > 0.5x | Too slow for near-real-time use cases |

### 4.4 Privacy / Compliance

- [ ] Deepgram DPA confirms zero data retention
- [ ] No audio or transcript data logged to Deepgram infrastructure after response
- [ ] API key stored in `.env` only, never committed to git

---

## 5. Go / No-Go Criteria

**Go** if ALL of the following are true:
1. Average WER < 10% across 3 recordings
2. Speaker count accurate or off by 1 in at least 2 of 3 recordings
3. Consistency score ≥ 0.80 on average
4. Deepgram DPA confirmed zero data retention
5. Latency acceptable for async processing (< 0.5x real-time factor)

**No-Go** if ANY of the following:
- Average WER > 20%
- Speaker diarization fails on 2+ recordings (off by 2+ speakers)
- Deepgram cannot confirm zero data retention in writing

**Conditional Go** (requires follow-up work):
- WER 10–20%: investigate audio quality, noise filtering, or alternative models
- Speaker count off by 1 consistently: acceptable for phase 1 if downstream NLP can handle it

---

## 6. Decision

> **PENDING HUMAN EXECUTION** — The test scripts are complete and ready to run, but
> require a human to provide real meeting recordings and a Deepgram API key.
> This section must be filled in after running `test_deepgram.py` and the
> evaluation scripts. The issue (FAR-6 / FAR-49–FAR-52) should remain In Progress
> until real results are entered below.

**Result:** [ ] Go / [ ] No-Go / [x] Conditional Go *(interim — pending data)*

**Rationale:** Code scaffolding is complete. Deepgram Nova-3 API, diarization, and
evaluation tooling are all implemented. A go/no-go decision requires actual WER and
diarization scores from real meeting recordings — these cannot be generated without
human-provided audio files and a live Deepgram API key.

**Next steps:**
1. Obtain Deepgram API key; add to `.env` (copy from `.env.example`)
2. Place 3+ real meeting recordings (`.mp3`, `.wav`, or `.m4a`) in `recordings/`
3. Run: `python test_deepgram.py`
4. Run: `python evaluate_accuracy.py`
5. Run: `python evaluate_diarization.py --expected-speakers N`
6. Fill in the results table in Section 3 and record final Go/No-Go above

---

## 7. Open Questions

- Does Deepgram Nova-3 handle meeting-specific jargon (product names, technical terms) better with a custom vocabulary/hints? If WER is marginal, test with `keywords` parameter.
- How does performance degrade for non-native English speakers? Farz users may include global teams.
- What is the fallback if Deepgram has an outage? Evaluate AssemblyAI or Whisper as alternatives.
