"""
FAR-51: Evaluate speaker diarization quality from Deepgram Nova-3 transcripts.

Usage:
    python evaluate_diarization.py [--expected-speakers N]

Prerequisites:
    - Run test_deepgram.py first to populate OUTPUT_DIR with transcript JSON files.
    - Diarization must have been enabled (diarize=True) — this is the default in test_deepgram.py.

Diarization quality rubric (go/no-go criteria):
  Speaker count accuracy:
    Exact match          — Excellent
    Off by 1             — Acceptable (common with brief side-speakers)
    Off by 2+            — Failing

  Speaker consistency score:
    > 0.90               — Excellent (few cross-speaker word assignments)
    0.75–0.90            — Acceptable
    < 0.75               — Failing (speakers are being confused)

  Avg words per turn:
    > 20 words/turn      — Good segmentation
    10–20 words/turn     — Acceptable
    < 10 words/turn      — Over-segmented; may cause issues for downstream summarisation
"""

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


# ---------------------------------------------------------------------------
# Diarization analysis helpers
# ---------------------------------------------------------------------------

def extract_words_with_speakers(response: dict) -> list[dict]:
    """Return the words array (each word has 'speaker', 'start', 'end', 'word')."""
    try:
        return response["results"]["channels"][0]["alternatives"][0]["words"]
    except (KeyError, IndexError, TypeError):
        return []


def compute_speaker_turns(words: list[dict]) -> list[dict]:
    """
    Group consecutive words by the same speaker into turns.
    Returns list of {speaker, word_count, start, end, words} dicts.
    """
    if not words:
        return []

    turns = []
    current_speaker = words[0].get("speaker")
    current_words = [words[0]]

    for word in words[1:]:
        spk = word.get("speaker")
        if spk == current_speaker:
            current_words.append(word)
        else:
            turns.append({
                "speaker": current_speaker,
                "word_count": len(current_words),
                "start": current_words[0].get("start"),
                "end": current_words[-1].get("end"),
            })
            current_speaker = spk
            current_words = [word]

    # Flush last turn
    turns.append({
        "speaker": current_speaker,
        "word_count": len(current_words),
        "start": current_words[0].get("start"),
        "end": current_words[-1].get("end"),
    })
    return turns


def compute_speaker_consistency(turns: list[dict]) -> float:
    """
    Naive consistency proxy: fraction of total words in the dominant
    continuous runs (i.e., ratio of words NOT in very short turns < 3 words).

    A low ratio suggests the model is fragmenting speakers erratically.
    Returns a float in [0, 1].
    """
    if not turns:
        return 0.0
    total_words = sum(t["word_count"] for t in turns)
    stable_words = sum(t["word_count"] for t in turns if t["word_count"] >= 3)
    return stable_words / total_words if total_words > 0 else 0.0


def rate_speaker_count_accuracy(detected: int, expected: Optional[int]) -> str:
    if expected is None:
        return "Unknown (no expected count provided)"
    diff = abs(detected - expected)
    if diff == 0:
        return "Excellent (exact match)"
    if diff == 1:
        return "Acceptable (off by 1)"
    return f"Failing (off by {diff})"


def rate_consistency(score: float) -> str:
    if score > 0.90:
        return "Excellent"
    if score >= 0.75:
        return "Acceptable"
    return "Failing"


def rate_avg_words_per_turn(avg: float) -> str:
    if avg > 20:
        return "Good"
    if avg >= 10:
        return "Acceptable"
    return "Over-segmented"


# ---------------------------------------------------------------------------
# Per-file evaluation
# ---------------------------------------------------------------------------

def evaluate_file(stem: str, response: dict, expected_speakers: Optional[int]) -> dict:
    words = extract_words_with_speakers(response)
    if not words:
        return {
            "file": stem,
            "error": "No word-level diarization data found. Was diarize=True used?",
        }

    # Speaker stats
    speaker_ids = {w.get("speaker") for w in words if w.get("speaker") is not None}
    speaker_count = len(speaker_ids)
    words_per_speaker = Counter()
    for w in words:
        spk = w.get("speaker")
        if spk is not None:
            words_per_speaker[spk] += 1

    # Turn analysis
    turns = compute_speaker_turns(words)
    total_turns = len(turns)
    avg_words_per_turn = round(sum(t["word_count"] for t in turns) / total_turns, 1) if total_turns else 0
    consistency_score = round(compute_speaker_consistency(turns), 3)

    # Flag if fewer than expected speakers
    underdiarized = (
        expected_speakers is not None and speaker_count < expected_speakers
    )

    metrics = {
        "file": stem,
        "detected_speakers": speaker_count,
        "expected_speakers": expected_speakers,
        "speaker_count_rating": rate_speaker_count_accuracy(speaker_count, expected_speakers),
        "total_turns": total_turns,
        "avg_words_per_turn": avg_words_per_turn,
        "avg_words_per_turn_rating": rate_avg_words_per_turn(avg_words_per_turn),
        "consistency_score": consistency_score,
        "consistency_rating": rate_consistency(consistency_score),
        "underdiarized_flag": underdiarized,
        "words_per_speaker": dict(words_per_speaker),
    }
    return metrics


def print_file_report(metrics: dict) -> None:
    stem = metrics["file"]
    if "error" in metrics:
        print(f"  File: {stem}.json — ERROR: {metrics['error']}\n")
        return

    print(f"  File: {stem}.json")
    print(f"    Detected speakers      : {metrics['detected_speakers']}")
    if metrics["expected_speakers"] is not None:
        print(f"    Expected speakers      : {metrics['expected_speakers']}")
    print(f"    Speaker count rating   : {metrics['speaker_count_rating']}")
    print(f"    Total turns            : {metrics['total_turns']}")
    print(f"    Avg words/turn         : {metrics['avg_words_per_turn']} ({metrics['avg_words_per_turn_rating']})")
    print(f"    Consistency score      : {metrics['consistency_score']} ({metrics['consistency_rating']})")
    if metrics.get("underdiarized_flag"):
        print(f"    *** FLAG: Fewer speakers detected than expected — possible under-diarization ***")
    print(f"    Words per speaker      : {metrics['words_per_speaker']}")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate Deepgram diarization quality.")
    parser.add_argument(
        "--expected-speakers",
        type=int,
        default=None,
        help="Expected number of unique speakers across all recordings (optional).",
    )
    args = parser.parse_args()

    output_dir = Path(os.environ.get("OUTPUT_DIR", "./transcripts_output"))
    if not output_dir.exists():
        print(f"ERROR: OUTPUT_DIR '{output_dir}' does not exist. Run test_deepgram.py first.", file=sys.stderr)
        sys.exit(1)

    json_files = sorted(
        p for p in output_dir.glob("*.json")
        if p.name not in {"run_summary.json", "evaluation_report.json", "diarization_report.json"}
    )

    if not json_files:
        print(f"No transcript JSON files found in '{output_dir}'. Run test_deepgram.py first.", file=sys.stderr)
        sys.exit(1)

    print(f"Evaluating diarization for {len(json_files)} transcript(s)...\n")

    all_metrics = []
    for json_path in json_files:
        try:
            with open(json_path, encoding="utf-8") as f:
                response = json.load(f)
        except json.JSONDecodeError as exc:
            print(f"  WARNING: Could not parse '{json_path.name}': {exc}", file=sys.stderr)
            continue

        metrics = evaluate_file(json_path.stem, response, args.expected_speakers)
        print_file_report(metrics)
        all_metrics.append(metrics)

    # Aggregate
    valid = [m for m in all_metrics if "error" not in m]
    if valid:
        avg_consistency = round(sum(m["consistency_score"] for m in valid) / len(valid), 3)
        avg_words_per_turn = round(sum(m["avg_words_per_turn"] for m in valid) / len(valid), 1)
        underdiarized_count = sum(1 for m in valid if m.get("underdiarized_flag"))

        print("--- Aggregate Diarization Summary ---")
        print(f"  Files evaluated        : {len(valid)}")
        print(f"  Avg consistency score  : {avg_consistency} ({rate_consistency(avg_consistency)})")
        print(f"  Avg words/turn         : {avg_words_per_turn} ({rate_avg_words_per_turn(avg_words_per_turn)})")
        print(f"  Under-diarized files   : {underdiarized_count}")

        aggregate = {
            "total_files": len(valid),
            "avg_consistency_score": avg_consistency,
            "avg_words_per_turn": avg_words_per_turn,
            "underdiarized_files": underdiarized_count,
            "files": all_metrics,
        }
    else:
        aggregate = {"total_files": 0, "files": all_metrics}

    report_path = output_dir / "diarization_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(aggregate, f, indent=2)

    print(f"\nDiarization report saved: {report_path}")


if __name__ == "__main__":
    main()
