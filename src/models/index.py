from __future__ import annotations

import datetime
import uuid

from pydantic import BaseModel, ConfigDict


class IndexBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    conversation_count: int = 0
    topic_count: int = 0
    commitment_count: int = 0
    last_updated: datetime.datetime
    google_access_token: str | None = None
    google_refresh_token: str | None = None


class IndexCreate(IndexBase):
    pass


class Index(IndexBase):
    id: uuid.UUID
    user_id: uuid.UUID
    created_at: datetime.datetime
