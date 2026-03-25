"""
Combined Celery worker entry point.

Imports all task modules so a single worker process can handle
ingest, extract, and embed tasks from the same Redis queue.

Usage:
    celery -A src.workers.combined worker --loglevel=info --concurrency=2
"""

from src.celery_app import celery_app  # noqa: F401 — worker entry point
from src.workers.embed import embed_conversation  # noqa: F401 — register task
from src.workers.extract import (  # noqa: F401 — register task
    backfill_knowledge_graph_for_user,
    backfill_segment_links_for_user,
    extract_from_conversation,
    rebuild_entity_nodes_for_user,
    rebuild_topic_nodes_for_user,
)
from src.workers.ingest import ingest_recording  # noqa: F401 — register task
from src.workers.tasks import (  # noqa: F401
    generate_brief,
    process_transcript,
    schedule_recurring_briefs,
    sync_calendar_artifacts,
)
