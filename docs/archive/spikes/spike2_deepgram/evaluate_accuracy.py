"""
FAR-50: Evaluate transcription accuracy against manual reference.

Usage:
    python evaluate_accuracy.py

Prerequisites:
    - Run test_deepgram.py first to populate OUTPUT_DIR with transcript JSON files.
    - For WER calculation: have a reference transcript ready as plain text.

This script reads every transcript JSON in OUTPUT_DIR and computes:
  - Average Deepgram confidence score
  - Word count per file
  - Optional WER (Word Error Rate) if you paste a reference transcript

WER rubric:
  < 5%   — Excellent. Production-ready for meeting summarisation.
  5–10%  — Acceptable. Minor post-processing may be needed.
  10–20% — Marginal. Verify whether audio quality is a contributing factor.
  > 20%  — Failing. Do not use Deepgram as sole STT provider without improvement.
"""

import json
import os
import sys
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


# ---------------------------------------------------------------------------
# WER helpers
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> list[str]:
    """Lowercase, strip punctuation, split into word tokens."""
    import re
    text = text.lower()
    text = re.sub(r"[^\w\s']", "", text)
    return text.split()


def compute_wer(reference: str, hypothesis: str) -> float:
    """
    Compute Word Error Rate using dynamic programming.

    WER = (S + D + I) / N
    where S = substitutions, D = deletions, I = insertions, N = reference words.
    Returns a float in [0, inf). Values > 1 are possible when hypothesis is much longer.
    """
    ref_tokens = _tokenize(reference)
    hyp_tokens = _tokenize(hypothesis)

    if not ref_tokens:
        raise ValueError("Reference transcript is empty — cannot compute WER.")

    n = len(ref_tokens)
    m = len(hyp_tokens)

    # dp[i][j] = edit distance between ref[:i] and hyp[:j]
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        dp[i][0] = i
    for j in range(m + 1):
        dp[0][j] = j

    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if ref_tokens[i - 1] == hyp_tokens[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = 1 + min(
                    dp[i - 1][j],     # deletion
                    dp[i][j - 1],     # insertion
                    dp[i - 1][j - 1], # substitution
                )

    return dp[n][m] / n


# ---------------------------------------------------------------------------
# Transcript parsing
# ---------------------------------------------------------------------------

def extract_transcript_text(response: dict) -> str:
    """Extract the full transcript string from a Deepgram response dict."""
    try:
        return response["results"]["channels"][0]["alternatives"][0]["transcript"]
    except (KeyError, IndexError, TypeError):
        return ""


def extract_confidence(response: dict) -> Optional[float]:
    """Extract the top-level confidence score from a Deepgram response dict."""
    try:
        return response["results"]["channels"][0]["alternatives"][0]["confidence"]
    except (KeyError, IndexError, TypeError):
        return None


def extract_word_count(response: dict) -> int:
    """Count words from the words array (more reliable than splitting transcript string)."""
    try:
        words = response["results"]["channels"][0]["alternatives"][0]["words"]
        return len(words)
    except (KeyError, IndexError, TypeError):
        return 0


# ---------------------------------------------------------------------------
# Main evaluation logic
# ---------------------------------------------------------------------------

def load_transcripts(output_dir: Path) -> list[tuple[str, dict]]:
    """Return list of (filename_stem, response_dict) for all JSON transcripts."""
    results = []
    for json_path in sorted(output_dir.glob("*.json")):
        if json_path.name == "run_summary.json":
            continue
        try:
            with open(json_path, encoding="utf-8") as f:
                data = json.load(f)
            results.append((json_path.stem, data))
        except json.JSONDecodeError as exc:
            print(f"  WARNING: Could not parse '{json_path.name}': {exc}", file=sys.stderr)
    return results


def prompt_reference_transcript(stem: str) -> Optional[str]:
    """Interactively ask the user for a reference transcript for WER calculation."""
    print(f"\n  [WER] Paste reference transcript for '{stem}'.")
    print("  (Press Enter twice when done, or type 'skip' to skip WER for this file.)")
    lines = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line.strip().lower() == "skip":
            return None
        if line == "" and lines and lines[-1] == "":
            break
        lines.append(line)
    text = "\n".join(lines).strip()
    return text if text else None


def evaluate(output_dir: Path, interactive: bool = True) -> dict:
    transcripts = load_transcripts(output_dir)
    if not transcripts:
        print(
            f"No transcript JSON files found in '{output_dir}'. "
            "Run test_deepgram.py first.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Evaluating {len(transcripts)} transcript(s) from '{output_dir}'...\n")

    file_metrics = []

    for stem, response in transcripts:
        word_count = extract_word_count(response)
        confidence = extract_confidence(response)
        transcript_text = extract_transcript_text(response)

        metric = {
            "file": stem,
            "word_count": word_count,
            "confidence": round(confidence, 4) if confidence is not None else None,
            "wer": None,
            "wer_rating": None,
        }

        print(f"  File: {stem}.json")
        print(f"    Word count  : {word_count}")
        print(f"    Confidence  : {confidence:.4f}" if confidence is not None else "    Confidence  : N/A")

        if interactive:
            ref = prompt_reference_transcript(stem)
            if ref:
                try:
                    wer = compute_wer(ref, transcript_text)
                    wer_pct = round(wer * 100, 2)
                    metric["wer"] = wer_pct

                    if wer_pct < 5:
                        rating = "Excellent"
                    elif wer_pct < 10:
                        rating = "Acceptable"
                    elif wer_pct < 20:
                        rating = "Marginal"
                    else:
                        rating = "Failing"
                    metric["wer_rating"] = rating

                    print(f"    WER         : {wer_pct}% ({rating})")
                except ValueError as exc:
                    print(f"    WER ERROR   : {exc}", file=sys.stderr)

        file_metrics.append(metric)
        print()

    # Aggregate stats
    confidences = [m["confidence"] for m in file_metrics if m["confidence"] is not None]
    wers = [m["wer"] for m in file_metrics if m["wer"] is not None]

    aggregate = {
        "total_files": len(file_metrics),
        "avg_confidence": round(sum(confidences) / len(confidences), 4) if confidences else None,
        "avg_wer_pct": round(sum(wers) / len(wers), 2) if wers else None,
        "files": file_metrics,
    }

    print("--- Aggregate ---")
    print(f"  Avg confidence : {aggregate['avg_confidence']}")
    print(f"  Avg WER        : {aggregate['avg_wer_pct']}%" if aggregate["avg_wer_pct"] is not None else "  Avg WER        : N/A (no reference transcripts provided)")

    return aggregate


def main() -> None:
    output_dir = Path(os.environ.get("OUTPUT_DIR", "./transcripts_output"))
    if not output_dir.exists():
        print(f"ERROR: OUTPUT_DIR '{output_dir}' does not exist. Run test_deepgram.py first.", file=sys.stderr)
        sys.exit(1)

    report = evaluate(output_dir, interactive=True)

    report_path = output_dir / "evaluation_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print(f"\nEvaluation report saved: {report_path}")


if __name__ == "__main__":
    main()
