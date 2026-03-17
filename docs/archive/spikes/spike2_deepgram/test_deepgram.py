"""
FAR-49: Test script — send recordings to Deepgram Nova-3.

Usage:
    pip install -r requirements.txt
    cp .env.example .env && edit .env with your API key
    python test_deepgram.py

Reads audio files from RECORDINGS_DIR, transcribes each with Deepgram Nova-3
(diarization + smart formatting enabled), and writes JSON results to OUTPUT_DIR.
"""

import json
import os
import sys
import time
from pathlib import Path

from deepgram import DeepgramClient, PrerecordedOptions, FileSource
from dotenv import load_dotenv

load_dotenv()

SUPPORTED_EXTENSIONS = {".mp3", ".wav", ".m4a"}


def load_config() -> tuple[str, Path, Path]:
    """Load and validate required environment variables at startup."""
    api_key = os.environ.get("DEEPGRAM_API_KEY", "").strip()
    if not api_key or api_key == "your_deepgram_api_key_here":
        print("ERROR: DEEPGRAM_API_KEY is not set. Add it to .env and retry.", file=sys.stderr)
        sys.exit(1)

    recordings_dir = Path(os.environ.get("RECORDINGS_DIR", "./recordings"))
    output_dir = Path(os.environ.get("OUTPUT_DIR", "./transcripts_output"))

    if not recordings_dir.exists():
        print(f"ERROR: RECORDINGS_DIR '{recordings_dir}' does not exist.", file=sys.stderr)
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)
    return api_key, recordings_dir, output_dir


def find_recordings(recordings_dir: Path) -> list[Path]:
    """Return all supported audio files in the recordings directory."""
    files = [
        f for f in recordings_dir.iterdir()
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
    ]
    return sorted(files)


def transcribe_file(client: DeepgramClient, audio_path: Path) -> dict:
    """
    Send a single audio file to Deepgram Nova-3 and return the raw response dict.
    Raises DeepgramApiError on API failure.
    """
    options = PrerecordedOptions(
        model="nova-3",
        diarize=True,
        punctuate=True,
        smart_format=True,
        language="en",
    )
    with open(audio_path, "rb") as f:
        audio_data = f.read()

    payload: FileSource = {"buffer": audio_data}
    response = client.listen.prerecorded.v("1").transcribe_file(payload, options)
    return response.to_dict()


def extract_summary_metrics(response: dict) -> dict:
    """Pull top-level metrics from a Deepgram response dict for console display."""
    try:
        results = response["results"]
        channels = results.get("channels", [])
        if not channels:
            return {"word_count": 0, "speaker_count": 0, "confidence": 0.0}

        channel = channels[0]
        alternatives = channel.get("alternatives", [])
        if not alternatives:
            return {"word_count": 0, "speaker_count": 0, "confidence": 0.0}

        best = alternatives[0]
        words = best.get("words", [])
        word_count = len(words)
        confidence = best.get("confidence", 0.0)

        # Speaker count from diarization: unique speaker values across all words
        speaker_ids = {w.get("speaker") for w in words if w.get("speaker") is not None}
        speaker_count = len(speaker_ids)

        return {
            "word_count": word_count,
            "speaker_count": speaker_count,
            "confidence": round(confidence, 4),
        }
    except (KeyError, IndexError, TypeError) as exc:
        return {"word_count": 0, "speaker_count": 0, "confidence": 0.0, "parse_error": str(exc)}


def process_recordings(api_key: str, recordings_dir: Path, output_dir: Path) -> None:
    """Iterate over all recordings, transcribe each, save JSON output."""
    recordings = find_recordings(recordings_dir)
    if not recordings:
        print(
            f"No audio files found in '{recordings_dir}'. "
            "Place .mp3 / .wav / .m4a files there and re-run.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Found {len(recordings)} recording(s). Transcribing with Deepgram Nova-3...\n")
    client = DeepgramClient(api_key)

    summary_rows = []

    for audio_path in recordings:
        print(f"  Processing: {audio_path.name}")
        start = time.monotonic()

        try:
            response = transcribe_file(client, audio_path)
        except Exception as exc:
            # Log the error with enough detail to diagnose; do not swallow silently.
            print(f"    ERROR transcribing '{audio_path.name}': {exc}", file=sys.stderr)
            summary_rows.append({
                "file": audio_path.name,
                "status": "error",
                "error": str(exc),
            })
            continue

        elapsed = round(time.monotonic() - start, 2)
        metrics = extract_summary_metrics(response)

        output_path = output_dir / f"{audio_path.stem}.json"
        with open(output_path, "w", encoding="utf-8") as out:
            json.dump(response, out, indent=2)

        row = {
            "file": audio_path.name,
            "status": "ok",
            "output": str(output_path),
            "word_count": metrics["word_count"],
            "speaker_count": metrics["speaker_count"],
            "confidence": metrics["confidence"],
            "elapsed_seconds": elapsed,
        }
        summary_rows.append(row)

        print(
            f"    Words: {metrics['word_count']} | "
            f"Speakers: {metrics['speaker_count']} | "
            f"Confidence: {metrics['confidence']} | "
            f"Time: {elapsed}s"
        )
        print(f"    Saved: {output_path}\n")

    # Write a run summary alongside the transcripts
    summary_path = output_dir / "run_summary.json"
    with open(summary_path, "w", encoding="utf-8") as sf:
        json.dump(summary_rows, sf, indent=2)

    ok_count = sum(1 for r in summary_rows if r["status"] == "ok")
    err_count = len(summary_rows) - ok_count
    print(f"Done. {ok_count} succeeded, {err_count} failed.")
    print(f"Run summary: {summary_path}")


if __name__ == "__main__":
    api_key, recordings_dir, output_dir = load_config()
    process_recordings(api_key, recordings_dir, output_dir)
