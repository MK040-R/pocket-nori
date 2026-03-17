"""
Celery configuration for Pocket Nori — Upstash Redis broker.

Reads UPSTASH_REDIS_URL from the settings singleton (fail-fast if missing).
All settings are tuned for reliability with a serverless Redis backend.
"""

import ssl
import sys
from typing import Any

from src.config import settings

# Read the Redis URL from the validated settings singleton.
# The settings object already performs startup validation — if UPSTASH_REDIS_URL
# is absent the process will have already exited before reaching this module.
# We still guard against running as a worker without a URL, matching the
# original spike behaviour for belt-and-suspenders safety.
REDIS_URL: str = settings.UPSTASH_REDIS_URL

_running_as_worker: bool = any(arg in sys.argv for arg in ("worker", "beat", "inspect", "control"))
if not REDIS_URL and _running_as_worker:
    raise OSError(
        "UPSTASH_REDIS_URL is not set. Copy .env.example to .env and add your Upstash Redis URL."
    )

broker_url: str = REDIS_URL
result_backend: str = REDIS_URL

# Explicit TLS configuration is required when using rediss:// URLs.
# Celery's Redis backend raises at runtime if ssl_cert_reqs is omitted.
broker_use_ssl: dict[str, Any] = {"ssl_cert_reqs": ssl.CERT_REQUIRED}
redis_backend_use_ssl: dict[str, Any] = {"ssl_cert_reqs": ssl.CERT_REQUIRED}

# Serialization — JSON only; never pickle (security + portability).
task_serializer: str = "json"
result_serializer: str = "json"
accept_content: list[str] = ["json"]

# Reliability: ack the message only after the task finishes (or raises).
# If the worker dies mid-task the message returns to the queue.
task_acks_late: bool = True
task_reject_on_worker_lost: bool = True
task_acks_on_failure_or_timeout: bool = True

# Retry defaults (individual tasks can override).
task_max_retries: int = 3
task_default_retry_delay: int = 30  # seconds

# Visibility timeout must be longer than the longest expected task.
# Upstash uses Redis LIST semantics: a task is invisible to other workers
# while being processed; if the worker dies before acking, it reappears
# after visibility_timeout seconds.
broker_transport_options: dict[str, Any] = {
    "visibility_timeout": 3600,  # 1 hour — adjust if tasks can run longer
    "retry_policy": {
        "timeout": 5.0,  # seconds before giving up on a broker connection attempt
    },
}

# Result expiry: discard stored results after 24 hours.
result_expires: int = 86400

# Prefetch: process one task at a time per worker process.
# Prevents a slow task from blocking faster ones and reduces duplicate work
# after a worker crash (fewer tasks were prefetched and un-acked).
worker_prefetch_multiplier: int = 1

# Beat schedule — periodic tasks.
beat_schedule: dict[str, Any] = {
    "prep-upcoming-meetings": {
        "task": "src.workers.prep.prep_upcoming_meetings",
        "schedule": 900.0,  # every 15 minutes
    },
}

# Auto-discover tasks in workers module.
imports: list[str] = [
    "src.workers.prep",
]
