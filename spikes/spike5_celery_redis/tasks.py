"""
Celery app and task definitions for Pocket Nori Spike 5.

Tasks defined here are deliberately simple — their purpose is to validate
Celery + Upstash Redis behaviour (dispatch, retry, visibility timeout,
worker recovery), not to implement production logic.
"""
import time

from celery import Celery

import celeryconfig

app = Celery("pocket-nori")
app.config_from_object(celeryconfig)


@app.task(bind=True, max_retries=3, default_retry_delay=5)
def process_transcript(self, transcript_id: str, user_id: str, content: str) -> dict:
    """Simulate processing a meeting transcript.

    Args:
        transcript_id: Unique identifier for the transcript.
        user_id: Owner of the transcript — used to enforce per-user isolation.
        content: Raw transcript text.

    Returns:
        A dict with processing metadata (word_count, status).

    Raises:
        ValueError: If required identifiers are missing.
    """
    if not transcript_id:
        raise ValueError("transcript_id is required and must be non-empty")
    if not user_id:
        raise ValueError("user_id is required and must be non-empty")

    # Simulate a short processing step (tokenisation, indexing, etc.)
    time.sleep(0.1)

    return {
        "transcript_id": transcript_id,
        "user_id": user_id,
        "word_count": len(content.split()),
        "status": "processed",
    }


@app.task(bind=True, max_retries=3, default_retry_delay=2)
def failing_task(self, should_fail: bool = True) -> dict:
    """Task that raises on its first attempt to exercise retry behaviour.

    On retry attempt 1+ it succeeds, so the final result confirms the task
    recovered without manual intervention.

    Args:
        should_fail: When True (default) the first attempt raises RuntimeError.

    Returns:
        A dict recording how many attempts were needed.
    """
    if should_fail and self.request.retries == 0:
        raise self.retry(
            exc=RuntimeError("Intentional first-attempt failure for retry testing"),
            countdown=1,  # retry quickly in tests
        )
    return {"attempts": self.request.retries + 1, "success": True}


@app.task(bind=True)
def slow_task(self, duration_seconds: float = 5.0) -> dict:
    """Long-running task for visibility timeout and worker-recovery testing.

    Sleeps for `duration_seconds` then returns.  In tests, a short duration
    (e.g. 2 s) is used so tests remain fast; longer durations simulate
    real workloads that exceed a worker's lifetime.

    Args:
        duration_seconds: How long to sleep before returning.

    Returns:
        A dict confirming completion and the actual duration requested.
    """
    time.sleep(duration_seconds)
    return {"completed": True, "duration": duration_seconds}
