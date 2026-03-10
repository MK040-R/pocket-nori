"""
Shared Celery application instance.

All worker modules import `celery_app` from here so that tasks
registered in different modules (ingest, extract, embed) are all
visible to a single combined worker process.
"""

from celery import Celery

from src import celeryconfig

celery_app = Celery("farz")
celery_app.config_from_object(celeryconfig)
