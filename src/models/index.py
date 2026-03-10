from __future__ import annotations

import uuid
import datetime

from pydantic import BaseModel, ConfigDict


class IndexBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    conversation_count: int = 0
    topic_count: int = 0
    commitment_count: int = 0
    last_updated: datetime.datetime


class IndexCreate(IndexBase):
    pass


class Index(IndexBase):
    id: uuid.UUID
    user_id: uuid.UUID
    created_at: datetime.datetime
