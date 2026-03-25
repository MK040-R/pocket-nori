"""Queue and poll the per-user rollout maintenance sequence.

Usage:
    python scripts/run_rollout_backfill.py \
      --api-base-url https://your-api.onrender.com \
      --bearer-token <supabase-access-token>

The script queues the four rollout jobs in the recommended order and polls
`GET /admin/jobs/{job_id}` until each job succeeds or fails.
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import Any

import httpx

ROLL_OUT_STEPS: tuple[tuple[str, str], ...] = (
    ("topic_nodes", "/topics/recluster"),
    ("segment_links", "/admin/backfill-segment-links"),
    ("entity_nodes", "/admin/rebuild-entity-nodes"),
    ("knowledge_graph", "/admin/backfill-knowledge-graph"),
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base-url", required=True, help="Pocket Nori API base URL")
    parser.add_argument(
        "--bearer-token",
        required=True,
        help="Supabase access token for the pilot user",
    )
    parser.add_argument(
        "--poll-interval-seconds",
        type=float,
        default=5.0,
        help="Polling interval while waiting on a job",
    )
    return parser.parse_args()


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def _echo(message: str) -> None:
    sys.stdout.write(f"{message}\n")
    sys.stdout.flush()


def _queue_step(client: httpx.Client, api_base_url: str, token: str, path: str) -> str:
    response = client.post(f"{api_base_url.rstrip('/')}{path}", headers=_headers(token))
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or "job_id" not in payload:
        raise RuntimeError(f"Unexpected queue response for {path}: {payload!r}")
    return str(payload["job_id"])


def _poll_job(
    client: httpx.Client,
    api_base_url: str,
    token: str,
    job_id: str,
    interval_seconds: float,
) -> dict[str, Any]:
    while True:
        response = client.get(
            f"{api_base_url.rstrip('/')}/admin/jobs/{job_id}",
            headers=_headers(token),
        )
        response.raise_for_status()
        payload = response.json()
        status = str(payload.get("status") or "")
        detail = str(payload.get("detail") or "")
        if detail:
            _echo(f"  status={status} detail={detail}")
        else:
            _echo(f"  status={status}")
        if status == "success":
            return payload
        if status == "failure":
            raise RuntimeError(f"Job {job_id} failed: {detail or payload}")
        time.sleep(interval_seconds)


def main() -> int:
    args = _parse_args()
    with httpx.Client(timeout=30.0) as client:
        for step_name, path in ROLL_OUT_STEPS:
            _echo(f"Queueing {step_name} via {path} ...")
            job_id = _queue_step(client, args.api_base_url, args.bearer_token, path)
            _echo(f"  job_id={job_id}")
            result = _poll_job(
                client,
                args.api_base_url,
                args.bearer_token,
                job_id,
                args.poll_interval_seconds,
            )
            _echo(f"  completed result={result.get('result') or {}}")
    _echo("Rollout backfill sequence completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
