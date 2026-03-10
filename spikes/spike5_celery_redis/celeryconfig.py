"""
Celery configuration for Farz Spike 5 — Upstash Redis broker.

Reads UPSTASH_REDIS_URL from environment (fail-fast if missing).
All settings are tuned for reliability with a serverless Redis backend.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# Read the Redis URL.  We use .get() here so that unit tests using
# ALWAYS_EAGER mode (no broker) can import this module without crashing.
# Integration tests and the live worker still fail fast — celery itself
# will raise a connection error the moment it tries to contact the broker.
# If you want strict startup validation, run:
#   python -c "import celeryconfig; assert celeryconfig.REDIS_URL"
REDIS_URL = os.environ.get("UPSTASH_REDIS_URL", "")
if not REDIS_URL:
    import sys
    # Only hard-fail when running as a worker/beat, not during module import
    # for tests.  Unit tests override task_always_eager and never connect.
    _running_as_worker = any(
        arg in sys.argv for arg in ("worker", "beat", "inspect", "control")
    )
    if _running_as_worker:
        raise EnvironmentError(
            "UPSTASH_REDIS_URL is not set. "
            "Copy .env.example to .env and add your Upstash Redis URL."
        )

broker_url = REDIS_URL
result_backend = REDIS_URL

# Serialization — JSON only; never pickle (security + portability).
task_serializer = "json"
result_serializer = "json"
accept_content = ["json"]

# Reliability: ack the message only after the task finishes (or raises).
# If the worker dies mid-task the message returns to the queue.
task_acks_late = True
task_reject_on_worker_lost = True
task_acks_on_failure_or_timeout = True

# Retry defaults (individual tasks can override).
task_max_retries = 3
task_default_retry_delay = 30  # seconds

# Visibility timeout must be longer than the longest expected task.
# Upstash uses Redis LIST semantics: a task is invisible to other workers
# while being processed; if the worker dies before acking, it reappears
# after visibility_timeout seconds.
broker_transport_options = {
    "visibility_timeout": 3600,  # 1 hour — adjust if tasks can run longer
    "retry_policy": {
        "timeout": 5.0,  # seconds before giving up on a broker connection attempt
    },
}

# Result expiry: discard stored results after 24 hours.
result_expires = 86400

# Prefetch: process one task at a time per worker process.
# Prevents a slow task from blocking faster ones and reduces duplicate work
# after a worker crash (fewer tasks were prefetched and un-acked).
worker_prefetch_multiplier = 1
