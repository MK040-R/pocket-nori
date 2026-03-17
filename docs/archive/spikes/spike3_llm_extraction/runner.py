"""
Batch runner: processes all .txt transcripts through all 3 extractors.

Usage:
    python runner.py

Results are saved to results/{transcript_stem}/topics.json,
commitments.json, and entities.json.
"""

import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from extractor import extract_commitments, extract_entities, extract_topics

TRANSCRIPTS_DIR = Path(__file__).parent / "transcripts"
RESULTS_DIR = Path(__file__).parent / "results"


def check_api_key() -> bool:
    if not os.getenv("ANTHROPIC_API_KEY"):
        print(
            "ERROR: ANTHROPIC_API_KEY is not set.\n"
            "  1. Copy .env.example to .env\n"
            "  2. Add your Anthropic API key\n"
            "  3. Re-run this script\n",
            file=sys.stderr,
        )
        return False
    return True


def process_transcript(transcript_path: Path) -> dict:
    transcript = transcript_path.read_text(encoding="utf-8")
    stem = transcript_path.stem
    out_dir = RESULTS_DIR / stem
    out_dir.mkdir(parents=True, exist_ok=True)

    start = time.monotonic()

    print(f"  [topics]       extracting...", end="", flush=True)
    topics = extract_topics(transcript)
    topics_path = out_dir / "topics.json"
    topics_path.write_text(topics.model_dump_json(indent=2), encoding="utf-8")
    print(f" {len(topics.topics)} found")

    print(f"  [commitments]  extracting...", end="", flush=True)
    commitments = extract_commitments(transcript)
    commitments_path = out_dir / "commitments.json"
    commitments_path.write_text(commitments.model_dump_json(indent=2), encoding="utf-8")
    print(f" {len(commitments.commitments)} found")

    print(f"  [entities]     extracting...", end="", flush=True)
    entities = extract_entities(transcript)
    entities_path = out_dir / "entities.json"
    entities_path.write_text(entities.model_dump_json(indent=2), encoding="utf-8")
    print(f" {len(entities.entities)} found")

    elapsed = time.monotonic() - start
    return {
        "transcript": transcript_path.name,
        "topics": len(topics.topics),
        "commitments": len(commitments.commitments),
        "entities": len(entities.entities),
        "elapsed_s": round(elapsed, 1),
    }


def print_summary(rows: list[dict]) -> None:
    header = f"{'Transcript':<40} {'Topics':>8} {'Commits':>9} {'Entities':>9} {'Time(s)':>8}"
    divider = "-" * len(header)
    print("\n" + divider)
    print(header)
    print(divider)
    for r in rows:
        print(
            f"{r['transcript']:<40} {r['topics']:>8} {r['commitments']:>9} "
            f"{r['entities']:>9} {r['elapsed_s']:>8}"
        )
    print(divider + "\n")


def main() -> None:
    if not check_api_key():
        sys.exit(1)

    transcript_files = sorted(TRANSCRIPTS_DIR.glob("*.txt"))
    if not transcript_files:
        print(
            f"No .txt files found in {TRANSCRIPTS_DIR}.\n"
            "Add transcript files and re-run.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Found {len(transcript_files)} transcript(s). Processing...\n")
    rows = []
    for tf in transcript_files:
        print(f"Processing: {tf.name}")
        try:
            row = process_transcript(tf)
            rows.append(row)
        except Exception as exc:
            print(f"  ERROR: {exc}", file=sys.stderr)
            rows.append(
                {
                    "transcript": tf.name,
                    "topics": "ERR",
                    "commitments": "ERR",
                    "entities": "ERR",
                    "elapsed_s": 0,
                }
            )

    print_summary(rows)
    print(f"Results saved to: {RESULTS_DIR}/")


if __name__ == "__main__":
    main()
